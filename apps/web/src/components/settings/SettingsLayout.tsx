import { useEffect, useState } from "react";

import { useCapabilities } from "../../hooks/useCapabilities";
import type { ThemePreference } from "../../hooks/useTheme";
import { type CredentialStatus, fetchCredentials } from "../../lib/credentials";
import type { SettingsSection } from "../../lib/routes";
import { fetchSettings, type SecretStatus, type SettingsView } from "../../lib/settings";
import { SettingsNav } from "./SettingsNav";
import {
  AppearanceSection,
  LlmSection,
  SourcesSection,
  SystemSection,
  ToolsSection,
  VideoSection,
  VoiceSection,
} from "./SettingsSections";
import type { SettingsSurface } from "./settingsSurface";
import { isLlmKeyless } from "../../lib/capabilities";
import styles from "./SettingsLayout.module.css";

interface SettingsLayoutProps {
  apiBaseUrl: string;
  /** The active sub-section (from the `/settings/:section` URL). */
  section: SettingsSection;
  /** The theme preference + setter, threaded through only for the Appearance section. */
  preference: ThemePreference;
  onPreferenceChange: (preference: ThemePreference) => void;
}

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; view: SettingsView };

/** The Settings surface: a persistent left sub-nav welded to the active section's content. One data
 *  load (settings + capabilities + — under BYOK — the credential vault) feeds every section through
 *  a shared `SettingsSurface`, so a key saved in one section flips capabilities and unlocks gated
 *  sections everywhere at once. Sections are URL-addressable (`/settings/:section`) for deep links
 *  and Back/Forward. Replaces the old flat `SettingsPanel` stack. */
export function SettingsLayout({
  apiBaseUrl,
  section,
  preference,
  onPreferenceChange,
}: SettingsLayoutProps) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [credentialStatuses, setCredentialStatuses] = useState<CredentialStatus[]>([]);
  // Bumped on every key save/remove — threaded into key-gated sections so they re-read the vault at
  // once (the bug that once made the cover toggle impossible to turn on without a reload).
  const [keysVersion, setKeysVersion] = useState(0);
  const { capabilities, reload: reloadCapabilities } = useCapabilities(apiBaseUrl);

  useEffect(() => {
    const controller = new AbortController();
    fetchSettings(apiBaseUrl, controller.signal)
      .then((view) => {
        if (controller.signal.aborted) return;
        setState({ status: "ready", view });
        // Under BYOK the per-user vault is the credential source; load its statuses once so every
        // section can render its own keys from one place.
        if (view.byokEnabled) {
          fetchCredentials(apiBaseUrl, controller.signal)
            .then((statuses) => !controller.signal.aborted && setCredentialStatuses(statuses))
            .catch(() => undefined); // a vault read failure leaves keys "not set" — never blocks Settings
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Could not load settings.",
        });
      });
    return () => controller.abort();
  }, [apiBaseUrl]);

  function onSecretSaved(updated: SecretStatus) {
    reloadCapabilities();
    setKeysVersion((v) => v + 1);
    setState((prev) =>
      prev.status === "ready"
        ? {
            status: "ready",
            view: {
              ...prev.view,
              secrets: prev.view.secrets.map((s) => (s.name === updated.name ? updated : s)),
            },
          }
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

  return (
    <div className={styles.layout}>
      <SettingsNav active={section} />
      <div className={styles.content}>
        <div className={styles.stack}>
          {state.status === "loading" && <p className={styles.muted}>Loading settings…</p>}
          {state.status === "error" && (
            <p className={styles.error} role="alert">
              {state.message}
            </p>
          )}
          {state.status === "ready" &&
            (() => {
              const surface: SettingsSurface = {
                apiBaseUrl,
                pipeline: state.view.pipeline,
                byokEnabled: state.view.byokEnabled,
                perUserConfigEnabled: state.view.perUserConfigEnabled,
                keyless: isLlmKeyless(capabilities),
                capabilities,
                secrets: state.view.secrets,
                credentialStatuses,
                keysVersion,
                onSecretSaved,
                onCredentialChanged,
              };
              switch (section) {
                case "system":
                  return <SystemSection surface={surface} />;
                case "appearance":
                  return (
                    <AppearanceSection
                      preference={preference}
                      onPreferenceChange={onPreferenceChange}
                    />
                  );
                case "llm":
                  return <LlmSection surface={surface} />;
                case "video":
                  return <VideoSection surface={surface} />;
                case "voice":
                  return <VoiceSection surface={surface} />;
                case "tools":
                  return <ToolsSection surface={surface} />;
                case "sources":
                  return <SourcesSection surface={surface} />;
              }
            })()}
        </div>
      </div>
    </div>
  );
}
