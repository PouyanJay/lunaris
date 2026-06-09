import { useEffect, useState } from "react";

import { fetchKeylessReadiness, type KeylessReadinessStatus } from "../lib/keylessReadiness";

/** How often to re-probe while the GPU is still waking. Matches the order of a cold start (tens of
 *  seconds) without hammering the endpoint — each probe also nudges a scale-from-zero replica along. */
const _POLL_INTERVAL_MS = 4000;

/** Tracks whether the keyless GPU is ready while `enabled` (e.g. during a keyless build). Polls
 *  `/api/keyless/readiness` and stops once the answer is settled (`ready` / `not_applicable`) — only
 *  the transient `provisioning` / `unreachable` states keep polling. Returns `null` until the first
 *  probe resolves. Best-effort: a failed probe leaves the last known status (no throw). */
export function useKeylessReadiness(
  apiBaseUrl: string,
  enabled: boolean,
): KeylessReadinessStatus | null {
  const [status, setStatus] = useState<KeylessReadinessStatus | null>(null);

  useEffect(() => {
    if (!enabled) {
      setStatus(null);
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const settled = (next: KeylessReadinessStatus | null): boolean =>
      next === "ready" || next === "not_applicable";

    const poll = async (): Promise<void> => {
      const next = await fetchKeylessReadiness(apiBaseUrl, controller.signal).catch(() => null);
      if (controller.signal.aborted) return;
      if (next !== null) setStatus(next);
      // Keep polling only while the state can still change (waking / not-yet-reachable).
      if (!settled(next)) timer = setTimeout(poll, _POLL_INTERVAL_MS);
    };
    void poll();

    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [apiBaseUrl, enabled]);

  return status;
}
