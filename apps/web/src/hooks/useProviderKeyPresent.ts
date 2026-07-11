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
        if (controller.signal.aborted) return;
        // The server not listing the provider AT ALL is lockstep drift (API BYOK_PROVIDERS vs this
        // client) — the gate would read false forever with zero signal. Make it loud in the console
        // so the next investigation starts here instead of at the network tab.
        if (!creds.some((c) => c.provider === provider)) {
          console.warn(
            `useProviderKeyPresent: /api/credentials does not list provider "${provider}" — ` +
              "the key can never read as set (API/web BYOK provider lists out of lockstep?)",
          );
        }
        setByokPresent(creds.some((c) => c.provider === provider && c.isSet));
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        // Best-effort: the section locks with its add-a-key hint — but say WHY in the console, so a
        // locked toggle caused by an auth/network failure is distinguishable from a missing key.
        console.warn(
          `useProviderKeyPresent: could not read /api/credentials for "${provider}" — treating the ` +
            "key as absent.",
          error,
        );
      });
    return () => controller.abort();
  }, [apiBaseUrl, byokEnabled, provider, keysVersion]);

  if (byokEnabled) return byokPresent;
  return secrets.some((s) => s.name === provider && s.isSet);
}
