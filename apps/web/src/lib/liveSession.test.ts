import { describe, expect, it } from "vitest";

import { answerTurn, loadSession, LiveSessionError, startSession } from "./liveSession";

const SESSION = {
  sessionId: "s1",
  graphId: "g1",
  status: "active",
  turns: [
    {
      seq: 1,
      move: { kind: "introduce", nodeId: "a", reason: "Opening concept." },
      tutor: "Let's start with Gravity.",
      runId: "r1",
      criterion: { kind: "explain", statement: "Explain gravity in your own words." },
      answer: null,
      grade: null,
    },
  ],
};

function withFetch<T>(response: Response, run: () => Promise<T>): Promise<T> {
  const original = globalThis.fetch;
  globalThis.fetch = (() => Promise.resolve(response)) as unknown as typeof fetch;
  return run().finally(() => {
    globalThis.fetch = original;
  });
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("liveSession — opening and resuming a session", () => {
  it("returns a session that is already teaching", async () => {
    const session = await withFetch(json(SESSION, 201), () => startSession("", "g1"));

    expect(session.sessionId).toBe("s1");
    // The move rides every turn: without it the transcript is prose nobody can explain the
    // choice of, which is the whole point of the director emitting its reasoning.
    const [first] = session.turns;
    expect(first?.move.kind).toBe("introduce");
    expect(first?.move.reason).toBe("Opening concept.");
  });

  it("sends an answer and gets the session back with the turn it produced", async () => {
    // The answered turn changes as well as gaining a successor, which is why the whole session
    // comes back rather than just the new turn.
    const answered = {
      ...SESSION,
      turns: [
        {
          ...SESSION.turns[0],
          answer: "It pulls things together.",
          grade: { kind: "partial", reason: "Nearly." },
        },
        {
          seq: 2,
          move: { kind: "retrieve", nodeId: "a", reason: "Coming back." },
          tutor: "Once more.",
          runId: "r2",
          criterion: null,
          answer: null,
          grade: null,
        },
      ],
    };

    const session = await withFetch(json(answered), () =>
      answerTurn("", "s1", "It pulls things together."),
    );

    expect(session.turns).toHaveLength(2);
    expect(session.turns[0]?.grade?.kind).toBe("partial");
  });

  it("resumes the session a reloaded tab was in", async () => {
    const session = await withFetch(json(SESSION), () => loadSession("", "s1"));

    expect(session.turns).toHaveLength(1);
  });

  it("surfaces the server's own words when it refuses", async () => {
    // "Map not found" and "storage is down" have different next steps for the learner, and a
    // status code has neither.
    await expect(
      withFetch(json({ detail: "Map not found" }, 404), () => startSession("", "gone")),
    ).rejects.toThrow(/Map not found/);
  });

  it("falls back to the status when a failure carries no message of ours", async () => {
    await expect(
      withFetch(new Response("nginx said no", { status: 502 }), () => startSession("", "g1")),
    ).rejects.toThrow(/HTTP 502/);
  });

  it("rejects a session it cannot read rather than handing a half-shape to the view", async () => {
    // The transcript maps over `turns` directly, so a payload missing it must fail here rather
    // than as a raw TypeError inside render.
    await expect(
      withFetch(json({ sessionId: "s1", graphId: "g1", status: "active" }), () =>
        loadSession("", "s1"),
      ),
    ).rejects.toBeInstanceOf(LiveSessionError);
  });

  it("reports an unreachable server as a session failure, not a crash", async () => {
    const original = globalThis.fetch;
    globalThis.fetch = (() => Promise.reject(new Error("offline"))) as unknown as typeof fetch;
    try {
      await expect(startSession("", "g1")).rejects.toBeInstanceOf(LiveSessionError);
    } finally {
      globalThis.fetch = original;
    }
  });
});
