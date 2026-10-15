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
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("http://api.test/api/healthz");
    // Always a fresh answer, and abortable (the timeout and the caller both rely on it).
    expect(init).toMatchObject({ cache: "no-store", signal: expect.any(AbortSignal) });
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

    let settled = false;
    const result = probeServiceHealth("http://api.test", { timeoutMs: 1_000 }).finally(() => {
      settled = true;
    });

    await vi.advanceTimersByTimeAsync(999);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);

    await expect(result).resolves.toBe(false);
  });

  it("reports unhealthy when the caller aborts the probe", async () => {
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
    const controller = new AbortController();

    const result = probeServiceHealth("http://api.test", { signal: controller.signal });
    controller.abort();

    await expect(result).resolves.toBe(false);
  });
});
