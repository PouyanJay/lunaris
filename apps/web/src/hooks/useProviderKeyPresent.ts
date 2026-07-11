import { useEffect, useState } from "react";

import { fetchCredentials } from "../lib/credentials";
import type { SecretStatus } from "../lib/settings";

/**
 * Whether the caller has a key for `provider` — the gate for a key-tiered feature (AI course covers
 * need OpenAI; video narration needs ElevenLabs). Under BYOK the per-user key lives in the vault
 * (read via `/api/credentials`); otherwise the file-store secret status carries it. Best-effort: a
 * failed read leaves it `false`, so the section locks with an add-a-key hint rather than crashing.
 *
 * `keysVersion` is the freshness signal: the Settings shell bumps it whenever a key is saved or
 * removed, which re-reads the vault. Without it the vault was read ONCE on mount, so a key added in
 * the same session never unlocked its feature — the toggle stayed disabled until a full page reload
 * (and while deep-link reloads 404'd, that meant it could never be turned on at all).
 */
export function useProviderKeyPresent(
  apiBaseUrl: string,
  byokEnabled: boolean,
  secrets: SecretStatus[],
  provider: string,
  keysVersion = 0,
): boolean {
  const [byokPresent, setByokPresent] = useState(false);

  useEffect(() => {
    if (!byokEnabled) return;
    const controller = new AbortController();
    void fetchCredentials(apiBaseUrl, controller.signal)
      .then((creds) => {
        if (!controller.signal.aborted) {
          setByokPresent(creds.some((c) => c.provider === provider && c.isSet));
        }
      })
      .catch(() => {
        /* best-effort: leave false so the section locks with the add-a-key hint */
      });
    return () => controller.abort();
  }, [apiBaseUrl, byokEnabled, provider, keysVersion]);

  if (byokEnabled) return byokPresent;
  return secrets.some((s) => s.name === provider && s.isSet);
}
