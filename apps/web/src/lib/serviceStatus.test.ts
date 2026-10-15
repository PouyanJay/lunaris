import { afterEach, describe, expect, it, vi } from "vitest";

import { probeServiceHealth } from "./serviceStatus";

describe("probeServiceHealth", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("reports healthy when the API's liveness probe answers 2xx", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"status":"ok"}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(probeServiceHealth("http://api.test")).resolves.toBe(true);
    expect(String(fetchMock.mock.calls[0]![0])).toBe("http://api.test/api/healthz");
  });

  it("reports unhealthy when the request fails outright (a stopped app sends no CORS headers)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(probeServiceHealth("http://api.test")).resolves.toBe(false);
  });

  it.each([404, 500, 503])("reports unhealthy on an HTTP %i", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status })));

    await expect(probeServiceHealth("http://api.test")).resolves.toBe(false);
  });

  it("reports unhealthy when the probe hangs past its timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("aborted", "AbortError")),
            );
          }),
      ),
    );

    const result = probeServiceHealth("http://api.test", { timeoutMs: 1_000 });
    await vi.advanceTimersByTimeAsync(1_000);

    await expect(result).resolves.toBe(false);
  });
});
