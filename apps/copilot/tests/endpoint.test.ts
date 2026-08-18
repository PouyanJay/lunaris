import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterEach, describe, expect, it } from "vitest";

import { BASE_PATH, LIVE_AGENT, SESSION_HEADER } from "../src/contract.js";
import { liveListener } from "../src/endpoint.js";

/** What the Python API received, so the hop's forwarding can be inspected rather than assumed. */
interface Received {
  path: string;
  authorization: string | undefined;
  body: Record<string, unknown>;
}

const running: Server[] = [];

afterEach(async () => {
  await Promise.all(
    running.splice(0).map(
      (server) =>
        new Promise<void>((done) => {
          // `close()` alone only stops NEW connections and waits for open ones to end on their own.
          // The streaming test below deliberately holds a response open, so on the regression it
          // exists to catch that socket never closes and teardown stalls to its own hook timeout —
          // turning a clear assertion failure into a confusing hang. Node >= 18.2; the package
          // floors at 20.
          server.closeAllConnections();
          server.close(() => done());
        }),
    ),
  );
});

/** Read from a stream until `marker` appears, or fail with a message rather than hanging.
 *
 *  The unbounded version blocks until vitest's default 5s timeout on exactly the regression this
 *  file is written to catch — reporting a timeout instead of "the frame never arrived". */
async function readUntil(response: Response, marker: string, timeoutMs = 2000): Promise<string> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let seen = "";
  const deadline = setTimeout(() => void reader.cancel(), timeoutMs);
  try {
    while (!seen.includes(marker)) {
      const { value, done } = await reader.read();
      if (done) break;
      seen += decoder.decode(value, { stream: true });
    }
  } finally {
    clearTimeout(deadline);
    await reader.cancel().catch(() => {});
  }
  if (!seen.includes(marker)) {
    throw new Error(
      `never saw ${JSON.stringify(marker)} within ${timeoutMs}ms — the hop is buffering the turn ` +
        `instead of streaming it. Saw: ${JSON.stringify(seen.slice(0, 200))}`,
    );
  }
  return seen;
}

async function listen(server: Server): Promise<string> {
  running.push(server);
  await new Promise<void>((ready) => server.listen(0, "127.0.0.1", ready));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}

/** A stand-in for the FastAPI AG-UI endpoint, speaking real SSE over a real socket.
 *
 *  A real server rather than a mocked `fetch`: the thing under test is an HTTP hop, and a mock
 *  would only assert that we called a function we wrote. */
function fakeApi(frames: object[], received: Received[]): Promise<string> {
  return listen(
    createServer((request, response) => {
      let raw = "";
      request.on("data", (chunk) => (raw += chunk));
      request.on("end", () => {
        received.push({
          path: request.url ?? "",
          authorization: request.headers.authorization,
          body: JSON.parse(raw || "{}") as Record<string, unknown>,
        });
        response.writeHead(200, { "content-type": "text/event-stream" });
        for (const frame of frames) {
          response.write(`data: ${JSON.stringify(frame)}\n\n`);
        }
        response.end();
      });
    }),
  );
}

/** The runtime under test, on its own socket — the shape `main.ts` boots. */
async function runtimeOver(apiBaseUrl: string): Promise<string> {
  const copilot = liveListener({ apiBaseUrl, allowedOrigins: ["http://app.test"] });
  return listen(createServer((request, response) => void copilot(request, response)));
}

function runOnce(runtimeUrl: string, headers: Record<string, string>): Promise<Response> {
  return fetch(`${runtimeUrl}${BASE_PATH}/agent/${LIVE_AGENT}/run`, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify({
      threadId: "thread-1",
      runId: "run-1",
      state: {},
      messages: [],
      tools: [],
      context: [],
      forwardedProps: {},
    }),
  });
}

const A_TAUGHT_TURN = [
  { type: "RUN_STARTED", threadId: "thread-1", runId: "run-1" },
  { type: "TEXT_MESSAGE_START", messageId: "m1", role: "assistant" },
  { type: "TEXT_MESSAGE_CONTENT", messageId: "m1", delta: "gradients" },
  { type: "TEXT_MESSAGE_END", messageId: "m1" },
  { type: "RUN_FINISHED", threadId: "thread-1", runId: "run-1" },
];

describe("the route shape the browser kit is told to speak", () => {
  // `apps/web` sets `useSingleEndpoint={false}` on `<CopilotKit>` — the kit then speaks REST routes
  // under the base path (`GET …/info`, `POST …/agent/live/run`) rather than `{"method": …}` bodies
  // to the bare base path. This side must serve exactly that shape, and refuse the other, or the
  // two separately deployed halves 404 each other in production while each passes its own suite —
  // which is what happened from T1 to T7 of live-generative-surfaces. Pinned over a real socket.
  it("lists the agent at GET …/info", async () => {
    const runtimeUrl = await runtimeOver("http://api.invalid");

    // The browser sends the session header on every request, discovery included, and the agent
    // factory needs it to name the session — as the real panel does (`<CopilotKit headers=…>`).
    const response = await fetch(`${runtimeUrl}${BASE_PATH}/info`, {
      headers: { [SESSION_HEADER]: "sess-1" },
    });

    expect(response.status).toBe(200);
    const info = (await response.json()) as { agents: Record<string, unknown> };
    expect(Object.keys(info.agents)).toEqual([LIVE_AGENT]);
  });

  it("refuses the single-endpoint probe at the bare base path", async () => {
    // The kit's *default* transport. Answering it would let a misconfigured browser build appear
    // to work here and fail on the first run; 404 keeps the drift loud on both sides.
    const runtimeUrl = await runtimeOver("http://api.invalid");

    const response = await fetch(`${runtimeUrl}${BASE_PATH}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ method: "info" }),
    });

    expect(response.status).toBe(404);
  });
});

describe("the runtime as a hop", () => {
  it("forwards a run to the session's own stream, as the learner who asked", async () => {
    // Arrange
    const received: Received[] = [];
    const runtimeUrl = await runtimeOver(await fakeApi(A_TAUGHT_TURN, received));

    // Act
    const response = await runOnce(runtimeUrl, {
      [SESSION_HEADER]: "sess-77",
      authorization: "Bearer learner-token",
    });
    await response.text();

    // Assert — the right session, as the right learner.
    expect(received).toHaveLength(1);
    expect(received[0]?.path).toBe("/api/live/sessions/sess-77/agui");
    expect(received[0]?.authorization).toBe("Bearer learner-token");
    // The AG-UI body is passed through rather than rebuilt: the run the browser started is the run
    // Python sees, which is what makes one id correlate across all three runtimes.
    expect(received[0]?.body.runId).toBe("run-1");
    expect(received[0]?.body.threadId).toBe("thread-1");
  });

  it("relays the tutor's words back to the browser", async () => {
    // Arrange
    const runtimeUrl = await runtimeOver(await fakeApi(A_TAUGHT_TURN, []));

    // Act
    const response = await runOnce(runtimeUrl, { [SESSION_HEADER]: "sess-77" });
    const body = await response.text();

    // Assert — anything less and the browser renders an empty turn while the API believes it
    // taught one.
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(body).toContain("gradients");
    expect(body).toContain("RUN_FINISHED");
  });

  it("streams as events arrive rather than buffering the turn", async () => {
    // The entire reason this transport exists. A hop that collected the whole run before answering
    // would be P2a's behaviour with more moving parts — and it would pass every other assertion
    // here, which is why this one holds the API's stream open and checks the first frame lands
    // while it is still open.
    const received: Received[] = [];
    let releaseSecondFrame: () => void = () => {};
    const held = new Promise<void>((resolve) => (releaseSecondFrame = resolve));

    const api = createServer((request, response) => {
      request.on("data", () => {});
      request.on("end", async () => {
        received.push({ path: request.url ?? "", authorization: undefined, body: {} });
        response.writeHead(200, { "content-type": "text/event-stream" });
        response.write(
          `data: ${JSON.stringify({ type: "RUN_STARTED", threadId: "thread-1", runId: "run-1" })}\n\n`,
        );
        response.write(
          `data: ${JSON.stringify({ type: "TEXT_MESSAGE_START", messageId: "m1", role: "assistant" })}\n\n`,
        );
        response.write(
          `data: ${JSON.stringify({ type: "TEXT_MESSAGE_CONTENT", messageId: "m1", delta: "early" })}\n\n`,
        );
        await held;
        response.write(
          `data: ${JSON.stringify({ type: "TEXT_MESSAGE_END", messageId: "m1" })}\n\n`,
        );
        response.write(
          `data: ${JSON.stringify({ type: "RUN_FINISHED", threadId: "thread-1", runId: "run-1" })}\n\n`,
        );
        response.end();
      });
    });
    const runtimeUrl = await runtimeOver(await listen(api));

    // Act — read only the first chunks, with the API's response deliberately still open.
    let seen = "";
    try {
      const response = await runOnce(runtimeUrl, { [SESSION_HEADER]: "sess-77" });
      seen = await readUntil(response, "early");
    } finally {
      // Released in a finally so the held-open API response is always completed, even when the
      // assertion or the read fails — otherwise a failure leaves a socket dangling and teardown
      // inherits the problem.
      releaseSecondFrame();
    }

    // Assert — the word reached the browser before the turn was over. A buffering hop fails
    // `readUntil` with a message naming the cause, rather than passing: the test depends on the
    // behaviour it asserts.
    expect(seen).toContain("early");
    expect(seen).not.toContain("RUN_FINISHED");
  });
});

describe("a refusal from the API, as the browser hears it (T9)", () => {
  /** A stand-in API that refuses the run before any frame, the shape FastAPI's ``failure_mapping``
   *  gives a session past its ceiling, a duplicate send, a stale answer, a closed session. */
  function refusingApi(status: number, detail: string): Promise<string> {
    return listen(
      createServer((request, response) => {
        request.on("data", () => {});
        request.on("end", () => {
          response.writeHead(status, { "content-type": "application/json" });
          response.end(JSON.stringify({ detail }));
        });
      }),
    );
  }

  function runErrorsIn(body: string): { message: string }[] {
    return body
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => JSON.parse(line.slice("data:".length)) as { type: string; message: string })
      .filter((event) => event.type === "RUN_ERROR");
  }

  it("carries the API's sentence, not the wire it came wrapped in", async () => {
    // Before this the browser read `HTTP 429: {"detail":"…"}`, the HTTP client's own error text,
    // status and JSON envelope and all, in the learner's alert. The sentence FastAPI wrote for the
    // learner is the whole of what should reach them, and it says what to do next (a ceiling says
    // "start a fresh session", a duplicate says "give it a moment"), so nothing here paraphrases it.
    // Asserted on what the *runtime* emits over a real socket, not on the agent's own error object:
    // the kit's runner is what turns a thrown error into the RUN_ERROR the browser sees.
    const detail =
      "This session has reached its cost ceiling, so it has stopped here. What you demonstrated is saved.";
    const runtimeUrl = await runtimeOver(await refusingApi(429, detail));

    const response = await runOnce(runtimeUrl, { [SESSION_HEADER]: "sess-77" });
    const body = await response.text();

    const errors = runErrorsIn(body);
    expect(errors).toHaveLength(1);
    expect(errors[0]?.message).toBe(detail);
  });

  it("still says something when the refusal carries no sentence", async () => {
    // A proxy in front of the API, or the API's own 500, answers with no `detail`. Empty would be
    // a RUN_ERROR the browser renders as "The turn could not be taken: " and nothing after it.
    const runtimeUrl = await runtimeOver(await refusingApi(502, ""));

    const response = await runOnce(runtimeUrl, { [SESSION_HEADER]: "sess-77" });
    const body = await response.text();

    const errors = runErrorsIn(body);
    expect(errors).toHaveLength(1);
    expect(errors[0]?.message).toMatch(/502/);
  });
});
