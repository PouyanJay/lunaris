/** How long the liveness probe may take before the API counts as unreachable. The API keeps a warm
 *  replica, so a healthy answer arrives in well under a second; a hang means it is not serving. */
const DEFAULT_TIMEOUT_MS = 8_000;

/** Whether the API is serving: `GET /api/healthz` answers 2xx within the timeout.
 *
 *  Anything else counts as down. When production is switched off the API's container app is
 *  stopped, and Azure answers without CORS headers, so the browser surfaces it as a failed fetch
 *  rather than a status. Plain `fetch` (not `authedFetch`): the probe is public and must not wait on
 *  the auth session. */
export async function probeServiceHealth(
  apiBaseUrl: string,
  { timeoutMs = DEFAULT_TIMEOUT_MS }: { timeoutMs?: number } = {},
): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
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
  }
}
