import { useId, useState } from "react";

import { useConfig } from "../../hooks/useConfig";
import { useConfigSaver, type SaveFeedback } from "../../hooks/useConfigSaver";
import {
  COVER_CONFIG_KEYS,
  VIDEO_CONFIG_KEYS,
  boolToConfigValue,
  type ConfigSetting,
} from "../../lib/config";
import { Button } from "../primitives/Button";
import { Select } from "../primitives/Select";
import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { Switch } from "../primitives/Switch";
import { SaveResult } from "./SaveResult";
import styles from "./Config.module.css";

interface ConfigPanelProps {
  apiBaseUrl: string;
  /** When true, the panel describes its settings as the signed-in user's own; when false, as
   *  process-wide operator config. (The settings rendered are whatever the API returns.) */
  perUserConfig?: boolean;
  /** The disclosure's eyebrow/title. Defaults to "Configuration" / "Runtime configuration". */
  eyebrow?: string;
  title?: string;
  /** Restrict to config keys matching this predicate — so one server-driven config list can be
   *  split across sub-nav sections (LLM models vs System observability). Video/cover keys are always
   *  excluded (they own dedicated sections). */
  filter?: (name: string) => boolean;
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

type Feedback = SaveFeedback;

/** The non-secret Configuration section: LangSmith tracing/project + the strong/worker model tiers,
 *  each shown with its current value + default. LangSmith vars are read at startup, so a change is
 *  flagged "restart to apply"; model vars take effect on the next build. The video settings render
 *  in their own Video section (the three-layer disclosure), so they're filtered out here. */
export function ConfigPanel({
  apiBaseUrl,
  perUserConfig = false,
  eyebrow = "Configuration",
  title = "Runtime configuration",
  filter,
}: ConfigPanelProps) {
  const { state, apply } = useConfig(apiBaseUrl);
  const { save, busy, feedback } = useConfigSaver(apiBaseUrl, apply);
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const settings =
    state.status === "ready"
      ? state.settings.filter(
          (setting) =>
            !VIDEO_CONFIG_KEYS.has(setting.name) &&
            !COVER_CONFIG_KEYS.has(setting.name) &&
            (filter?.(setting.name) ?? true),
        )
      : [];

  return (
    <CollapsibleSection eyebrow={eyebrow} title={title} defaultOpen={false}>
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
          {settings.map((setting) => (
            <ConfigRow
              key={setting.name}
              setting={setting}
              busy={busy[setting.name] ?? false}
              feedback={feedback[setting.name]}
              draft={drafts[setting.name]}
              onDraft={(value) => setDrafts((prev) => ({ ...prev, [setting.name]: value }))}
              onSave={(value) =>
                save(setting.name, value, { restartRequired: setting.restartRequired })
              }
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
            onChange={(checked) => onSave(boolToConfigValue(checked))}
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

      <SaveResult feedback={feedback} />
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

function ModelControl({ id, setting, busy, onSave }: ControlProps) {
  const options = [...new Set<string>([...KNOWN_MODELS, setting.value])];
  return (
    <div className={styles.control}>
      <Select
        id={id}
        value={setting.value}
        options={options.map((model) => ({ value: model, label: model }))}
        onChange={onSave}
        disabled={busy}
        aria-labelledby={`${id}-label`}
      />
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
