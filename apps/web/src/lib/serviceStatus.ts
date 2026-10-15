/** How long the liveness probe may take before the API counts as unreachable: a probe that hangs
 *  this long means the API is not serving. */
const DEFAULT_TIMEOUT_MS = 8_000;

/** Whether the API is serving: `GET /api/healthz` answers 2xx within the timeout.
 *
 *  Anything else counts as down. When production is switched off the API's container app is
 *  stopped, and Azure answers without CORS headers, so the browser surfaces it as a failed fetch
 *  rather than a status. Plain `fetch` (not `authedFetch`): the probe is public and must not wait on
 *  the auth session. A caller's `signal` ends the probe early (as unhealthy). */
export async function probeServiceHealth(
  apiBaseUrl: string,
  { timeoutMs = DEFAULT_TIMEOUT_MS, signal }: { timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const forwardAbort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", forwardAbort);
  try {
    const response = await fetch(`${apiBaseUrl}/api/healthz`, {
      cache: "no-store",
      signal: controller.signal,
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
  }
}
