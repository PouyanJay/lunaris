import { afterEach, describe, expect, it, vi } from "vitest";

import { compileGraph, LiveGraphError } from "./liveGraph";

// Auth not configured in tests → authedFetch delegates to the global fetch, which we stub.
function stubFetch(impl: (url: string, init?: RequestInit) => unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => impl(String(url), init)),
  );
}

const GRAPH = {
  graphId: "g1",
  topic: "How neural networks learn",
  version: 1,
  nodes: [
    { id: "a", name: "Derivative as slope", definition: "…", requires: [], provenance: "compiled" },
    { id: "b", name: "Gradient", definition: "…", requires: ["a"], provenance: "compiled" },
  ],
  topoOrder: ["a", "b"],
  isAcyclic: true,
};

describe("liveGraph lib", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("compiles a topic into a concept graph", async () => {
    let captured: { url: string; init: RequestInit | undefined } | null = null;
    stubFetch((url, init) => {
      captured = { url, init };
      return { ok: true, json: async () => GRAPH };
    });

    const graph = await compileGraph("http://test", "How neural networks learn");

    expect(graph.nodes.map((node) => node.name)).toEqual(["Derivative as slope", "Gradient"]);
    expect(captured!.url).toBe("http://test/api/live/graphs");
    expect(captured!.init?.method).toBe("POST");
    expect(JSON.parse(String(captured!.init?.body))).toEqual({
      topic: "How neural networks learn",
    });
  });

  it("rejects with a LiveGraphError when the compile fails", async () => {
    stubFetch(() => ({ ok: false, status: 500, text: async () => "boom" }));

    await expect(compileGraph("http://test", "Tides")).rejects.toBeInstanceOf(LiveGraphError);
  });

  it("rejects an alien payload rather than handing it to the map", async () => {
    // Trust boundary: the map reads node fields unguarded, so a shape check belongs here.
    stubFetch(() => ({ ok: true, json: async () => ({ graphId: "g1", nodes: "not-a-list" }) }));

    await expect(compileGraph("http://test", "Tides")).rejects.toBeInstanceOf(LiveGraphError);
  });
});
