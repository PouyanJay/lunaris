import { useEffect, useState } from "react";

import { fetchSettings, type SecretStatus, type SettingsView } from "../../lib/settings";
import { Button } from "../primitives/Button";
import { SecretField } from "./SecretField";
import styles from "./Settings.module.css";

interface SettingsPanelProps {
  apiBaseUrl: string;
  onClose: () => void;
}

const FIELDS = [
  {
    name: "anthropic",
    label: "Anthropic API key",
    hint: "Required for live course generation (real Claude). Validated when you save.",
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
] as const;

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; view: SettingsView };

/** The settings surface: enter API keys (write-only — only set/unset + last4 is ever shown)
 *  and see the current pipeline mode. */
export function SettingsPanel({ apiBaseUrl, onClose }: SettingsPanelProps) {
  const [state, setState] = useState<State>({ status: "loading" });

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
      <section className={styles.panel} aria-labelledby="settings-heading">
        <header className={styles.header}>
          <div>
            <span className="eyebrow">Settings</span>
            <h2 id="settings-heading" className={styles.title}>
              Keys &amp; configuration
            </h2>
          </div>
          <Button type="button" onClick={onClose}>
            Done
          </Button>
        </header>

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
      </section>
    </div>
  );
}
