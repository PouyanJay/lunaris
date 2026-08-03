import { describe, expect, it } from "vitest";

import { LiveGraphError } from "./liveGraph";
import { streamGraph, type CompileProgress } from "./streamGraph";

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
      new Response(body, {
        headers: { "content-type": "text/event-stream", "x-run-id": "r1" },
      }),
    )) as unknown as typeof fetch;
}

const GRAPH = {
  graphId: "g1",
  topic: "Tides",
  version: 1,
  nodes: [{ id: "a", name: "Gravity", definition: "Mass pulls.", requires: [] }],
  topoOrder: ["a"],
  isAcyclic: true,
};

async function withFetch<T>(frames: string[], run: () => Promise<T>): Promise<T> {
  const original = globalThis.fetch;
  globalThis.fetch = mockFetch(sseStream(frames));
  try {
    return await run();
  } finally {
    globalThis.fetch = original;
  }
}

describe("streamGraph — watching a compile happen", () => {
  it("reports each beat as it arrives and resolves with the finished map", async () => {
    const frames = [
      'event: progress\ndata: {"phase":"decomposing","done":0,"total":0}\n\n',
      'event: progress\ndata: {"phase":"authoring","done":1,"total":3}\n\n',
      `event: graph\ndata: ${JSON.stringify(GRAPH)}\n\n`,
    ];
    const beats: CompileProgress[] = [];

    const graph = await withFetch(frames, () =>
      streamGraph("", "Tides", { onProgress: (beat) => beats.push(beat) }),
    );

    expect(beats).toEqual([
      { phase: "decomposing", done: 0, total: 0 },
      { phase: "authoring", done: 1, total: 3 },
    ]);
    expect(graph.graphId).toBe("g1");
  });

  it("hands the run id over before any frame, so a failed compile can still be traced", async () => {
    let runId: string | undefined;

    await withFetch([`event: graph\ndata: ${JSON.stringify(GRAPH)}\n\n`], () =>
      streamGraph("", "Tides", { onRunId: (id) => (runId = id) }),
    );

    expect(runId).toBe("r1");
  });

  it("surfaces the server's own words when the compile fails mid-stream", async () => {
    // The status code was sent before the failure happened, so the message can only arrive as a
    // frame — and it is the server's, not a generic one invented here.
    const frames = [
      'event: progress\ndata: {"phase":"decomposing","done":0,"total":0}\n\n',
      'event: error\ndata: {"message":"Couldn\'t map this topic. Try again, or rephrase it.","runId":"r1"}\n\n',
    ];

    await expect(withFetch(frames, () => streamGraph("", "Tides", {}))).rejects.toThrow(
      /rephrase it/,
    );
  });

  it("treats a stream that stops before the map as a failure, not as an empty map", async () => {
    // A dropped connection must never render as "this topic has no concepts in it".
    const frames = ['event: progress\ndata: {"phase":"authoring","done":2,"total":9}\n\n'];

    await expect(withFetch(frames, () => streamGraph("", "Tides", {}))).rejects.toBeInstanceOf(
      LiveGraphError,
    );
  });

  it("rejects a map it cannot read rather than handing a half-shape to the view", async () => {
    const frames = ['event: graph\ndata: {"graphId":"g1","topic":"Tides"}\n\n'];

    await expect(withFetch(frames, () => streamGraph("", "Tides", {}))).rejects.toBeInstanceOf(
      LiveGraphError,
    );
  });
});
