import { useCallback, useEffect, useRef, useState } from "react";

import { probeServiceHealth } from "../lib/serviceStatus";

/** Whether the API is serving, probed once at load.
 *
 *  Optimistic: the app renders immediately and only `offline` flips when the probe fails, so a
 *  healthy load pays no extra round trip and sees no state change. */
export function useServiceStatus(apiBaseUrl: string): { offline: boolean } {
  const [offline, setOffline] = useState(false);
  const mounted = useRef(true);

  const probe = useCallback(async () => {
    const healthy = await probeServiceHealth(apiBaseUrl);
    if (mounted.current && !healthy) setOffline(true);
  }, [apiBaseUrl]);

  useEffect(() => {
    mounted.current = true;
    void probe();
    return () => {
      mounted.current = false;
    };
  }, [probe]);

  return { offline };
}
