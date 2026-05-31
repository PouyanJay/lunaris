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
});
