import { useCallback, useEffect, useRef, useState } from "react";

import { probeServiceHealth } from "../lib/serviceStatus";

/** How often an offline page re-checks, so it returns to the app by itself once production is on. */
const RECHECK_INTERVAL_MS = 15_000;

interface ServiceStatus {
  /** The API did not answer its liveness probe. */
  offline: boolean;
  /** A manual re-check is in flight. */
  checking: boolean;
  /** Re-probe now (the offline page's Try again). */
  recheck: () => void;
}

/** Whether the API is serving: probed once at load, then every 15s while it is not.
 *
 *  Optimistic: the app renders immediately and `offline` only flips when a probe fails, so a healthy
 *  load pays no extra round trip and sees no state change. */
export function useServiceStatus(apiBaseUrl: string): ServiceStatus {
  const [offline, setOffline] = useState(false);
  const [checking, setChecking] = useState(false);
  const inFlight = useRef(new Set<AbortController>());

  const probe = useCallback(async () => {
    const controller = new AbortController();
    inFlight.current.add(controller);
    try {
      const healthy = await probeServiceHealth(apiBaseUrl, { signal: controller.signal });
      if (!controller.signal.aborted) setOffline(!healthy);
    } finally {
      inFlight.current.delete(controller);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    const pending = inFlight.current;
    void probe();
    return () => pending.forEach((controller) => controller.abort());
  }, [probe]);

  useEffect(() => {
    if (!offline) return;
    const timer = setInterval(() => void probe(), RECHECK_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [offline, probe]);

  const recheck = useCallback(() => {
    setChecking(true);
    void probe().finally(() => setChecking(false));
  }, [probe]);

  return { offline, checking, recheck };
}
