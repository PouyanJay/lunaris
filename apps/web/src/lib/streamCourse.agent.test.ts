import { describe, expect, it } from "vitest";

import { streamCourse } from "./streamCourse";
import type { AgentEvent, Course } from "../types/course";

function sseStream(frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
}

function mockFetch(body: ReadableStream<Uint8Array>): typeof fetch {
  return (() =>
    Promise.resolve(
      new Response(body, { headers: { "content-type": "text/event-stream" } }),
    )) as unknown as typeof fetch;
}

const COURSE: Course = {
  id: "c1",
  topic: "Binary search",
  goalConcept: "binary_search",
  goalType: "knowledge",
  scopeNote: "",
  graph: { nodes: [], edges: [], frontier: [], isAcyclic: true, topoOrder: [] },
  modules: [],
  provenance: [],
  status: "published",
};

describe("streamCourse — agent transcript frames", () => {
  it("dispatches event:agent frames to onAgent, interleaved with progress, then resolves", async () => {
    const frames = [
      'event: progress\ndata: {"stage":"run_started","label":"Starting"}\n\n',
      'event: agent\ndata: {"kind":"tool_call","runId":"r1","sequence":0,"tool":"extract_concepts","toolArgs":{"topic":"Binary search"},"text":null,"result":null,"todos":null}\n\n',
      `event: course\ndata: ${JSON.stringify(COURSE)}\n\n`,
    ];
    const original = globalThis.fetch;
    globalThis.fetch = mockFetch(sseStream(frames));
    const agentEvents: AgentEvent[] = [];
    const stages: string[] = [];
    try {
      const course = await streamCourse("", "Binary search", {
        onProgress: (e) => stages.push(e.stage),
        onAgent: (e) => agentEvents.push(e),
      });

      expect(course.status).toBe("published");
      expect(stages).toEqual(["run_started"]);
      expect(agentEvents).toHaveLength(1);
      expect(agentEvents[0]?.kind).toBe("tool_call");
      expect(agentEvents[0]?.tool).toBe("extract_concepts");
      expect(agentEvents[0]?.toolArgs).toEqual({ topic: "Binary search" });
    } finally {
      globalThis.fetch = original;
    }
  });

  it("ignores keepalive heartbeat comment frames and still resolves the course", async () => {
    // The build emits `: keepalive` SSE comments during silent stretches to keep the connection
    // alive; the reader must skip them (no handler, no broken parse) and still resolve the course.
    const frames = [
      'event: progress\ndata: {"stage":"run_started","label":"Starting"}\n\n',
      ": keepalive\n\n",
      ": keepalive\n\n",
      'event: progress\ndata: {"stage":"run_completed","label":"Published"}\n\n',
      `event: course\ndata: ${JSON.stringify(COURSE)}\n\n`,
    ];
    const original = globalThis.fetch;
    globalThis.fetch = mockFetch(sseStream(frames));
    const stages: string[] = [];
    const agentEvents: AgentEvent[] = [];
    try {
      const course = await streamCourse("", "Binary search", {
        onProgress: (e) => stages.push(e.stage),
        onAgent: (e) => agentEvents.push(e),
      });

      // The heartbeats are invisible: only the two real progress stages dispatch, no agent beats,
      // and the terminal course still resolves.
      expect(stages).toEqual(["run_started", "run_completed"]);
      expect(agentEvents).toHaveLength(0);
      expect(course.status).toBe("published");
    } finally {
      globalThis.fetch = original;
    }
  });

  it("tolerates a heartbeat comment split across two stream chunks", async () => {
    // The keepalive can arrive split across TCP/stream chunks; the buffer-accumulating reader must
    // reassemble the frame and still ignore it (and not mistake the partial for a frame boundary).
    const chunks = [
      'event: progress\ndata: {"stage":"run_started","label":"Starting"}\n\n',
      ": keepa",
      "live\n\n",
      `event: course\ndata: ${JSON.stringify(COURSE)}\n\n`,
    ];
    const original = globalThis.fetch;
    globalThis.fetch = mockFetch(sseStream(chunks));
    const stages: string[] = [];
    try {
      const course = await streamCourse("", "Binary search", {
        onProgress: (e) => stages.push(e.stage),
      });

      expect(stages).toEqual(["run_started"]);
      expect(course.status).toBe("published");
    } finally {
      globalThis.fetch = original;
    }
  });
});

describe("streamCourse — clarification query param (P7.5)", () => {
  function captureUrl(): { calledUrl: () => string; restore: () => void } {
    const original = globalThis.fetch;
    let url = "";
    globalThis.fetch = ((input: string) => {
      url = String(input);
      const body = sseStream([`event: course\ndata: ${JSON.stringify(COURSE)}\n\n`]);
      return Promise.resolve(
        new Response(body, { headers: { "content-type": "text/event-stream" } }),
      );
    }) as unknown as typeof fetch;
    return { calledUrl: () => url, restore: () => (globalThis.fetch = original) };
  }

  it("rides the confirmed clarification as a JSON query param when present", async () => {
    const { calledUrl, restore } = captureUrl();
    try {
      await streamCourse("", "English", {
        clarification: { targetLevel: "advanced", assumedKnown: "grammar" },
      });

      const params = new URL(calledUrl(), "http://test").searchParams;
      expect(params.get("topic")).toBe("English");
      expect(JSON.parse(params.get("clarification") ?? "null")).toEqual({
        targetLevel: "advanced",
        assumedKnown: "grammar",
      });
    } finally {
      restore();
    }
  });

  it("omits the clarification param on the default (unpersonalized) path", async () => {
    const { calledUrl, restore } = captureUrl();
    try {
      await streamCourse("", "English", {});

      expect(new URL(calledUrl(), "http://test").searchParams.has("clarification")).toBe(false);
    } finally {
      restore();
    }
  });
});
