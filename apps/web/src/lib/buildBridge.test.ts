import { afterEach, describe, expect, it, vi } from "vitest";

import { runBuildBridgeWorker } from "./buildBridge";
import type { ChatMessage } from "./deviceEngine";

/** A scripted fetch: each call shifts the next handler off the queue; extra calls fail loudly. */
function scriptedFetch(handlers: Array<(url: string, init?: RequestInit) => Response>) {
  const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const handler = handlers.shift();
    if (!handler) throw new Error(`unexpected fetch: ${url}`);
    return handler(url, init);
  });
  vi.stubGlobal("fetch", mock);
  return { calls };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

const fakeEngine = (reply = "answered") => ({
  chat: vi.fn(async (_messages: ChatMessage[]) => reply),
});

describe("runBuildBridgeWorker", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("answers claimed completions until the run ends", async () => {
    // Arrange — one poll offering two requests, then the run ends (404 on the next poll).
    const engine = fakeEngine();
    const { calls } = scriptedFetch([
      () =>
        json([
          { requestId: "r1", messages: [{ role: "user", content: "one" }] },
          { requestId: "r2", messages: [{ role: "user", content: "two" }] },
        ]),
      () => new Response(null, { status: 204 }),
      () => new Response(null, { status: 204 }),
      () => new Response(null, { status: 404 }),
    ]);

    // Act
    await runBuildBridgeWorker({
      apiBaseUrl: "http://api",
      runId: "run-1",
      engine,
      signal: new AbortController().signal,
      retryDelayMs: 0,
    });

    // Assert — each request ran on the engine and its result was posted with its own id, to the
    // run's results endpoint, from a long-poll matching the server's window.
    expect(engine.chat).toHaveBeenCalledTimes(2);
    expect(engine.chat).toHaveBeenNthCalledWith(1, [{ role: "user", content: "one" }]);
    expect(calls[0]?.url).toBe("http://api/api/runs/run-1/bridge/requests?wait=25");
    const posts = calls.filter((c) => c.init?.method === "POST");
    expect(posts.map((c) => JSON.parse(String(c.init?.body)))).toEqual([
      { requestId: "r1", text: "answered" },
      { requestId: "r2", text: "answered" },
    ]);
    expect(posts[0]?.url).toBe("http://api/api/runs/run-1/bridge/results");
    expect(posts[1]?.url).toBe("http://api/api/runs/run-1/bridge/results");
  });

  it("keeps polling through empty claims", async () => {
    // Arrange — two empty windows, then a request, then the run ends.
    const engine = fakeEngine();
    scriptedFetch([
      () => json([]),
      () => json([]),
      () => json([{ requestId: "r1", messages: [{ role: "user", content: "x" }] }]),
      () => new Response(null, { status: 204 }),
      () => new Response(null, { status: 404 }),
    ]);

    // Act
    await runBuildBridgeWorker({
      apiBaseUrl: "http://api",
      runId: "run-1",
      engine,
      signal: new AbortController().signal,
      retryDelayMs: 0,
    });

    // Assert
    expect(engine.chat).toHaveBeenCalledTimes(1);
  });

  it("stops when the run ends (first poll 404s)", async () => {
    // Arrange
    const engine = fakeEngine();
    scriptedFetch([() => new Response(null, { status: 404 })]);

    // Act
    await runBuildBridgeWorker({
      apiBaseUrl: "http://api",
      runId: "run-1",
      engine,
      signal: new AbortController().signal,
      retryDelayMs: 0,
    });

    // Assert — nothing ran, nothing was posted.
    expect(engine.chat).not.toHaveBeenCalled();
  });

  it("stops when aborted instead of polling forever", async () => {
    // Arrange — the first poll aborts (the learner navigated away mid-window).
    const controller = new AbortController();
    const engine = fakeEngine();
    scriptedFetch([
      () => {
        controller.abort();
        throw new DOMException("aborted", "AbortError");
      },
    ]);

    // Act — resolves rather than retrying the aborted poll.
    await runBuildBridgeWorker({
      apiBaseUrl: "http://api",
      runId: "run-1",
      engine,
      signal: controller.signal,
      retryDelayMs: 0,
    });

    // Assert
    expect(engine.chat).not.toHaveBeenCalled();
  });

  it("retries after a transient poll failure", async () => {
    // Arrange — a network blip, then a served request, then the run ends.
    const engine = fakeEngine();
    scriptedFetch([
      () => {
        throw new TypeError("network down");
      },
      () => json([{ requestId: "r1", messages: [{ role: "user", content: "x" }] }]),
      () => new Response(null, { status: 204 }),
      () => new Response(null, { status: 404 }),
    ]);

    // Act
    await runBuildBridgeWorker({
      apiBaseUrl: "http://api",
      runId: "run-1",
      engine,
      signal: new AbortController().signal,
      retryDelayMs: 0,
    });

    // Assert — the blip didn't kill the worker; the request was still served.
    expect(engine.chat).toHaveBeenCalledTimes(1);
  });

  it("skips an already-answered completion (409) and keeps serving", async () => {
    // Arrange — the post conflicts (another tab answered first), then the run ends.
    const engine = fakeEngine();
    scriptedFetch([
      () => json([{ requestId: "r1", messages: [{ role: "user", content: "x" }] }]),
      () => new Response(null, { status: 409 }),
      () => new Response(null, { status: 404 }),
    ]);

    // Act / Assert — no throw; the loop continued to the next poll.
    await runBuildBridgeWorker({
      apiBaseUrl: "http://api",
      runId: "run-1",
      engine,
      signal: new AbortController().signal,
      retryDelayMs: 0,
    });
  });
});
