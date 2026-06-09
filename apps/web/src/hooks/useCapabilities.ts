import { useCallback, useEffect, useState } from "react";

import { type CapabilityStatus, fetchCapabilities } from "../lib/capabilities";

/** Tracks the per-capability live/fallback status, with a `reload` so a key change (set in Settings)
 *  flips a capability back to live and the Draft banner clears. Best-effort: errors leave the list
 *  empty (no banner) rather than surfacing into the shell. */
export function useCapabilities(apiBaseUrl: string): {
  capabilities: CapabilityStatus[];
  reload: () => void;
} {
  const [capabilities, setCapabilities] = useState<CapabilityStatus[]>([]);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchCapabilities(apiBaseUrl, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) setCapabilities(next);
      })
      .catch(() => {
        /* best-effort — leave the list empty so the banner simply doesn't show */
      });
    return () => controller.abort();
  }, [apiBaseUrl, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { capabilities, reload };
}
