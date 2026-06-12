import { afterEach, describe, expect, it, vi } from "vitest";

import { ExplainError, explainBlob } from "./explain";

describe("explainBlob", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts the blob (with context) and resolves with the explanation", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ explanation: "It orders concepts." }) });
    vi.stubGlobal("fetch", fetchMock);

    const result = await explainBlob("http://api", '{"x":1}', "Graph");

    // Provenance defaults to hosted when an (older) server omits source.
    expect(result).toEqual({ explanation: "It orders concepts.", source: "hosted" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api/api/explain");
    expect(JSON.parse(init.body)).toEqual({ content: '{"x":1}', context: "Graph" });
  });

  it("omits context from the body when not given", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ explanation: "ok" }) });
    vi.stubGlobal("fetch", fetchMock);

    await explainBlob("http://api", "{}");

    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({ content: "{}" });
  });

  it("rejects with ExplainError on a non-OK response (e.g. 503 no key)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));

    await expect(explainBlob("http://api", "{}")).rejects.toBeInstanceOf(ExplainError);
  });

  it("rejects with ExplainError when the network is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(explainBlob("http://api", "{}")).rejects.toBeInstanceOf(ExplainError);
  });
});
