import { useId, useState } from "react";

import { useConfig } from "../../hooks/useConfig";
import { ConfigError, updateConfig, type ConfigSetting } from "../../lib/config";
import { Button } from "../primitives/Button";
import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { Switch } from "../primitives/Switch";
import styles from "./Config.module.css";

interface ConfigPanelProps {
  apiBaseUrl: string;
  /** When true, the panel describes its settings as the signed-in user's own; when false, as
   *  process-wide operator config. (The settings rendered are whatever the API returns.) */
  perUserConfig?: boolean;
}

const LABELS: Record<string, string> = {
  langsmithTracing: "LangSmith tracing",
  langsmithProject: "LangSmith project",
  modelStrong: "Strong model",
  modelWorker: "Worker model",
};

const DESCRIPTIONS: Record<string, string> = {
  langsmithTracing: "Send agent traces to LangSmith for observability.",
  langsmithProject: "The LangSmith project traces are grouped under.",
  modelStrong: "Claude model for curriculum architecture and the strong-tier steps.",
  modelWorker: "Claude model for bulk extraction, judging, and authoring.",
};

// Known Claude model ids for the dropdown; the current value is always included even if newer.
const KNOWN_MODELS = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"] as const;

type Feedback = { tone: "ok" | "error"; message: string };

/** The non-secret Configuration section: LangSmith tracing/project + the strong/worker model tiers,
 *  each shown with its current value + default. LangSmith vars are read at startup, so a change is
 *  flagged "restart to apply"; model vars take effect on the next build. */
export function ConfigPanel({ apiBaseUrl, perUserConfig = false }: ConfigPanelProps) {
  const { state, apply } = useConfig(apiBaseUrl);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [feedback, setFeedback] = useState<Record<string, Feedback>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  async function save(name: string, value: string, restartRequired: boolean) {
    setBusy((prev) => ({ ...prev, [name]: true }));
    setFeedback(({ [name]: _removed, ...rest }) => rest);
    try {
      apply(await updateConfig(apiBaseUrl, name, value));
      const message = restartRequired ? "Saved — restart to apply" : "Saved";
      setFeedback((prev) => ({ ...prev, [name]: { tone: "ok", message } }));
    } catch (error: unknown) {
      const message = error instanceof ConfigError ? error.message : "Couldn't save.";
      setFeedback((prev) => ({ ...prev, [name]: { tone: "error", message } }));
    } finally {
      setBusy((prev) => ({ ...prev, [name]: false }));
    }
  }

  return (
    <CollapsibleSection eyebrow="Configuration" title="Runtime configuration" defaultOpen={false}>
      <p className={styles.muted}>
        {perUserConfig
          ? "The Claude models your own builds use."
          : "Operator configuration applied to every build on this server."}
      </p>
      {state.status === "loading" && <p className={styles.muted}>Loading configuration…</p>}
      {state.status === "error" && (
        <div className={styles.stateBlock} role="alert">
          <p className={styles.error}>{state.message}</p>
        </div>
      )}
      {state.status === "ready" && (
        <div className={styles.rows}>
          {state.settings.map((setting) => (
            <ConfigRow
              key={setting.name}
              setting={setting}
              busy={busy[setting.name] ?? false}
              feedback={feedback[setting.name]}
              draft={drafts[setting.name]}
              onDraft={(value) => setDrafts((prev) => ({ ...prev, [setting.name]: value }))}
              onSave={(value) => save(setting.name, value, setting.restartRequired)}
            />
          ))}
        </div>
      )}
    </CollapsibleSection>
  );
}

interface ConfigRowProps {
  setting: ConfigSetting;
  busy: boolean;
  feedback: Feedback | undefined;
  draft: string | undefined;
  onDraft: (value: string) => void;
  onSave: (value: string) => void;
}

function ConfigRow({ setting, busy, feedback, draft, onDraft, onSave }: ConfigRowProps) {
  const controlId = useId();
  const hintId = useId();
  const labelId = `${controlId}-label`;

  return (
    <div className={styles.row}>
      <div className={styles.head}>
        <label className={styles.label} htmlFor={controlId} id={labelId}>
          {LABELS[setting.name] ?? setting.name}
        </label>
        {setting.kind === "toggle" && (
          <Switch
            id={controlId}
            checked={setting.value === "true"}
            disabled={busy}
            aria-labelledby={labelId}
            aria-describedby={hintId}
            onChange={(checked) => onSave(checked ? "true" : "false")}
          />
        )}
      </div>

      {DESCRIPTIONS[setting.name] && (
        <p id={hintId} className={styles.hint}>
          {DESCRIPTIONS[setting.name]}
        </p>
      )}

      {setting.kind === "model" && (
        <ModelControl
          id={controlId}
          hintId={hintId}
          setting={setting}
          busy={busy}
          onSave={onSave}
        />
      )}
      {setting.kind === "text" && (
        <TextControl
          id={controlId}
          hintId={hintId}
          setting={setting}
          busy={busy}
          draft={draft}
          onDraft={onDraft}
          onSave={onSave}
        />
      )}

      <div className={styles.meta}>
        <span className={styles.default}>default: {setting.default}</span>
        {setting.restartRequired && <span className={styles.restart}>restart to apply</span>}
      </div>

      {feedback && (
        <p
          className={feedback.tone === "error" ? styles.error : styles.ok}
          role={feedback.tone === "error" ? "alert" : "status"}
        >
          {feedback.message}
        </p>
      )}
    </div>
  );
}

interface ControlProps {
  id: string;
  hintId: string;
  setting: ConfigSetting;
  busy: boolean;
  onSave: (value: string) => void;
}

function ModelControl({ id, hintId, setting, busy, onSave }: ControlProps) {
  const options = [...new Set<string>([...KNOWN_MODELS, setting.value])];
  return (
    <div className={styles.control}>
      <select
        id={id}
        className={styles.select}
        value={setting.value}
        disabled={busy}
        aria-describedby={hintId}
        onChange={(event) => onSave(event.target.value)}
      >
        {options.map((model) => (
          <option key={model} value={model}>
            {model}
          </option>
        ))}
      </select>
    </div>
  );
}

function TextControl({
  id,
  hintId,
  setting,
  busy,
  draft,
  onDraft,
  onSave,
}: ControlProps & { draft: string | undefined; onDraft: (value: string) => void }) {
  return (
    <div className={styles.control}>
      <input
        id={id}
        className={styles.input}
        value={draft ?? setting.value}
        disabled={busy}
        autoComplete="off"
        spellCheck={false}
        aria-describedby={hintId}
        onChange={(event) => onDraft(event.target.value)}
      />
      <Button type="button" onClick={() => onSave(draft ?? setting.value)} disabled={busy}>
        {busy ? "Saving…" : "Save"}
      </Button>
    </div>
  );
}
