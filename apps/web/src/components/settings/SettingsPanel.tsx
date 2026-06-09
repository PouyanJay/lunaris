import { useEffect, useState } from "react";

import { useCapabilities } from "../../hooks/useCapabilities";
import { fetchSettings, type SecretStatus, type SettingsView } from "../../lib/settings";
import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { CapabilityBadges } from "./CapabilityBadges";
import { ConfigPanel } from "./ConfigPanel";
import { CredentialsPanel } from "./CredentialsPanel";
import { SecretField } from "./SecretField";
import { TrustedSourcesPanel } from "./TrustedSourcesPanel";
import styles from "./Settings.module.css";

interface SettingsPanelProps {
  apiBaseUrl: string;
}

const FIELDS = [
  {
    name: "anthropic",
    label: "Anthropic API key",
    hint: "Required for live course generation (real Claude). Validated when you save. Choose the Claude models in Runtime configuration below.",
    placeholder: "sk-ant-…",
  },
  {
    name: "voyage",
    label: "Voyage embeddings key",
    hint: "Enables grounded claim verification against the corpus (optional).",
    placeholder: "pa-…",
  },
  {
    name: "supabaseUrl",
    label: "Supabase URL",
    hint: "The local data layer endpoint.",
    placeholder: "http://127.0.0.1:54321",
  },
  {
    name: "supabaseServiceRole",
    label: "Supabase service-role key",
    hint: "Service key for the data layer (grounding corpus).",
    placeholder: "sb_secret_…",
  },
  {
    name: "search",
    label: "Search API key (Tavily)",
    hint: "Enables research, auto-discovery, resources, and the seed feed (optional).",
    placeholder: "tvly-…",
  },
  {
    name: "youtube",
    label: "YouTube API key",
    hint: "Richer video resources (duration / channel) — optional; falls back to search.",
    placeholder: "AIza…",
  },
  {
    name: "langsmith",
    label: "LangSmith API key",
    hint: "Tracing/observability (optional). Read at startup — restart to apply.",
    placeholder: "lsv2_…",
  },
] as const;

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; view: SettingsView };

/** The settings surface: enter API keys (write-only — only set/unset + last4 is ever shown)
 *  and see the current pipeline mode. */
export function SettingsPanel({ apiBaseUrl }: SettingsPanelProps) {
  const [state, setState] = useState<State>({ status: "loading" });
  // Per-capability badges; reloaded when a key is saved so a capability flips live immediately.
  const { capabilities, reload: reloadCapabilities } = useCapabilities(apiBaseUrl);

  useEffect(() => {
    const controller = new AbortController();
    fetchSettings(apiBaseUrl, controller.signal)
      .then((view) => setState({ status: "ready", view }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Could not load settings.",
        });
      });
    return () => controller.abort();
  }, [apiBaseUrl]);

  function onSaved(updated: SecretStatus) {
    reloadCapabilities();
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

  return (
    <div className={styles.center}>
      <div className={styles.stack}>
        <CollapsibleSection eyebrow="Settings" title="Keys & configuration" defaultOpen={false}>
          {state.status === "loading" && <p className={styles.muted}>Loading settings…</p>}
          {state.status === "error" && (
            <p className={styles.error} role="alert">
              {state.message}
            </p>
          )}
          {state.status === "ready" && (
            <>
              <p className={styles.pipeline}>
                Pipeline mode: <span className="mono">{state.view.pipeline}</span>
              </p>
              <CapabilityBadges capabilities={capabilities} />
              {/* When BYOK is on, each tenant manages their own keys via the authed per-user
                  credentials API; otherwise the single-tenant file-backed secret store is used. */}
              {state.view.byokEnabled ? (
                <CredentialsPanel apiBaseUrl={apiBaseUrl} />
              ) : (
                <>
                  <div className={styles.fields}>
                    {FIELDS.map((field) => (
                      <SecretField
                        key={field.name}
                        apiBaseUrl={apiBaseUrl}
                        name={field.name}
                        label={field.label}
                        hint={field.hint}
                        placeholder={field.placeholder}
                        status={state.view.secrets.find((s) => s.name === field.name)}
                        onSaved={onSaved}
                      />
                    ))}
                  </div>
                  <p className={styles.note}>
                    Keys are stored on the backend and never sent back to the browser — only whether
                    they&rsquo;re set and the last four characters are shown.
                  </p>
                </>
              )}
            </>
          )}
        </CollapsibleSection>
        <TrustedSourcesPanel apiBaseUrl={apiBaseUrl} />
        <ConfigPanel
          apiBaseUrl={apiBaseUrl}
          perUserConfig={state.status === "ready" && state.view.perUserConfigEnabled}
        />
      </div>
    </div>
  );
}
