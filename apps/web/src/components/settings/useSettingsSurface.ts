import { useEffect, useState } from "react";

import { useCapabilities } from "../../hooks/useCapabilities";
import { isLlmKeyless } from "../../lib/capabilities";
import { type CredentialStatus, fetchCredentials } from "../../lib/credentials";
import { fetchSettings, type SecretStatus, type SettingsView } from "../../lib/settings";
import type { SettingsSurface } from "./settingsSurface";

/** The loaded settings surface, or the state to render instead. */
export type SettingsSurfaceState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; surface: SettingsSurface };

/** Loads and owns the shared settings state for every sub-nav section: the settings view, the
 *  per-capability providers, and — under BYOK — the credential vault, plus the `keysVersion`
 *  freshness signal and the save handlers that reload capabilities on every key change. Returns a
 *  ready `SettingsSurface` (or the loading/error state), so `SettingsLayout` is left with just the
 *  nav + section render. Extracted from the layout so that component stays single-purpose. */
export function useSettingsSurface(apiBaseUrl: string): SettingsSurfaceState {
  const [view, setView] = useState<SettingsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [credentialStatuses, setCredentialStatuses] = useState<CredentialStatus[]>([]);
  // Bumped on every key save/remove — threaded into key-gated sections so they re-read the vault at
  // once (the bug that once made the cover toggle impossible to turn on without a reload).
  const [keysVersion, setKeysVersion] = useState(0);
  const { capabilities, reload: reloadCapabilities } = useCapabilities(apiBaseUrl);

  useEffect(() => {
    const controller = new AbortController();
    fetchSettings(apiBaseUrl, controller.signal)
      .then((loaded) => {
        if (controller.signal.aborted) return;
        setView(loaded);
        // Under BYOK the per-user vault is the credential source; load its statuses once so every
        // section can render its own keys from one place.
        if (loaded.byokEnabled) {
          fetchCredentials(apiBaseUrl, controller.signal)
            .then((statuses) => !controller.signal.aborted && setCredentialStatuses(statuses))
            .catch(() => undefined); // a vault read failure leaves keys "not set" — never blocks Settings
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Could not load settings.");
      });
    return () => controller.abort();
  }, [apiBaseUrl]);

  function onSecretSaved(updated: SecretStatus) {
    reloadCapabilities();
    setKeysVersion((v) => v + 1);
    setView((prev) =>
      prev
        ? { ...prev, secrets: prev.secrets.map((s) => (s.name === updated.name ? updated : s)) }
        : prev,
    );
  }

  function onCredentialChanged(updated: CredentialStatus) {
    reloadCapabilities();
    setKeysVersion((v) => v + 1);
    setCredentialStatuses((prev) =>
      prev.some((s) => s.provider === updated.provider)
        ? prev.map((s) => (s.provider === updated.provider ? updated : s))
        : [...prev, updated],
    );
  }

  if (error !== null) return { status: "error", message: error };
  if (view === null) return { status: "loading" };
  return {
    status: "ready",
    surface: {
      apiBaseUrl,
      pipeline: view.pipeline,
      byokEnabled: view.byokEnabled,
      perUserConfigEnabled: view.perUserConfigEnabled,
      keyless: isLlmKeyless(capabilities),
      capabilities,
      secrets: view.secrets,
      credentialStatuses,
      keysVersion,
      onSecretSaved,
      onCredentialChanged,
    },
  };
}
