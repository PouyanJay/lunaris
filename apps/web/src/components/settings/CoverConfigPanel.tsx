import { useEffect, useId, useMemo, useState } from "react";

import { useConfig } from "../../hooks/useConfig";
import { useConfigSaver, type SaveFeedback } from "../../hooks/useConfigSaver";
import {
  COVER_MASTER_KEY,
  COVER_PRESET_KEY,
  COVER_STYLE_PRESETS,
  boolToConfigValue,
  type ConfigSetting,
} from "../../lib/config";
import { fetchCredentials } from "../../lib/credentials";
import type { SecretStatus } from "../../lib/settings";
import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { Switch } from "../primitives/Switch";
import { SaveResult } from "./SaveResult";
import styles from "./Config.module.css";

interface CoverConfigPanelProps {
  apiBaseUrl: string;
  /** Whether per-user BYOK is on — decides where the OpenAI key status is read from. */
  byokEnabled: boolean;
  /** The file-store secret statuses (the non-BYOK path's source for the OpenAI key). */
  secrets: SecretStatus[];
}

const PRESET_LABELS: Record<string, string> = {
  nocturne: "Nocturne — night-sky editorial (default)",
  blueprint: "Blueprint — technical line-art",
  aurora: "Aurora — soft abstract gradient",
};

/** The Cover section of Settings (course-cover-images T10): a master toggle for auto-generating an
 *  AI cover at build time, and — when on — the art-direction preset. AI covers need an OpenAI key
 *  (GPT Image 2), so without one the section is deactivated with a needs-a-key affordance and the
 *  account shows the Typographic cover instead. */
export function CoverConfigPanel({ apiBaseUrl, byokEnabled, secrets }: CoverConfigPanelProps) {
  const { state, apply } = useConfig(apiBaseUrl);
  const { save, busy, feedback } = useConfigSaver(apiBaseUrl, apply);
  const keyPresent = useOpenAiKeyPresent(apiBaseUrl, byokEnabled, secrets);

  const byName = useMemo(
    () =>
      state.status === "ready"
        ? new Map(state.settings.map((setting) => [setting.name, setting]))
        : new Map<string, ConfigSetting>(),
    [state],
  );
  const master = byName.get(COVER_MASTER_KEY);
  const preset = byName.get(COVER_PRESET_KEY);
  const masterOn = keyPresent && master?.value === "true";

  return (
    <CollapsibleSection eyebrow="Covers" title="Cover images" defaultOpen={false}>
      {state.status === "loading" && <p className={styles.hint}>Loading…</p>}
      {state.status === "error" && (
        <p className={styles.notice} role="alert">
          Couldn&rsquo;t load cover settings. {state.message}
        </p>
      )}
      {master && (
        <div className={styles.rows}>
          {keyPresent ? (
            <ToggleRow
              setting={master}
              busy={busy[COVER_MASTER_KEY] ?? false}
              feedback={feedback[COVER_MASTER_KEY]}
              onToggle={(on) => save(COVER_MASTER_KEY, boolToConfigValue(on))}
            />
          ) : (
            <KeylessCoverNotice master={master} />
          )}
          {masterOn && preset && (
            <PresetRow
              setting={preset}
              busy={busy[COVER_PRESET_KEY] ?? false}
              feedback={feedback[COVER_PRESET_KEY]}
              onSave={(value) => save(COVER_PRESET_KEY, value)}
            />
          )}
        </div>
      )}
    </CollapsibleSection>
  );
}

function KeylessCoverNotice({ master }: { master: ConfigSetting }) {
  const controlId = useId();
  const labelId = `${controlId}-label`;
  return (
    <div className={styles.row}>
      <div className={styles.head}>
        <span className={styles.label} id={labelId}>
          Generate cover images
        </span>
        <Switch
          id={controlId}
          checked={false}
          disabled
          aria-labelledby={labelId}
          onChange={() => {}}
        />
      </div>
      <p className={styles.notice} role="note">
        AI cover images need an OpenAI API key — add one in Keys above. Without it, courses show a
        Typographic cover. ({master.default === "true" ? "On by default once keyed." : ""})
      </p>
    </div>
  );
}

interface ToggleRowProps {
  setting: ConfigSetting;
  busy: boolean;
  feedback: SaveFeedback | undefined;
  onToggle: (on: boolean) => void;
}

function ToggleRow({ setting, busy, feedback, onToggle }: ToggleRowProps) {
  const controlId = useId();
  const hintId = useId();
  const labelId = `${controlId}-label`;
  return (
    <div className={styles.row}>
      <div className={styles.head}>
        <label className={styles.label} htmlFor={controlId} id={labelId}>
          Generate cover images
        </label>
        <Switch
          id={controlId}
          checked={setting.value === "true"}
          disabled={busy}
          aria-labelledby={labelId}
          aria-describedby={hintId}
          onChange={onToggle}
        />
      </div>
      <p id={hintId} className={styles.hint}>
        Art-direct a topic-relevant cover for each course you build. Off shows the Typographic
        cover.
      </p>
      <SaveResult feedback={feedback} />
    </div>
  );
}

interface PresetRowProps {
  setting: ConfigSetting;
  busy: boolean;
  feedback: SaveFeedback | undefined;
  onSave: (value: string) => void;
}

function PresetRow({ setting, busy, feedback, onSave }: PresetRowProps) {
  const controlId = useId();
  const labelId = `${controlId}-label`;
  // Include the stored value so a preset the UI doesn't list (an operator default) still shows.
  const options = [...new Set<string>([...COVER_STYLE_PRESETS, setting.value])];
  return (
    <div className={styles.row}>
      <div className={styles.head}>
        <label className={styles.label} htmlFor={controlId} id={labelId}>
          Art-direction style
        </label>
        <select
          id={controlId}
          className={styles.lengthSelect}
          value={setting.value}
          disabled={busy}
          aria-labelledby={labelId}
          onChange={(event) => onSave(event.target.value)}
        >
          {options.map((value) => (
            <option key={value} value={value}>
              {PRESET_LABELS[value] ?? value}
            </option>
          ))}
        </select>
      </div>
      <SaveResult feedback={feedback} />
    </div>
  );
}

/** Whether the caller has an OpenAI key — the gate for AI cover generation. Under BYOK the per-user
 *  key lives in the vault (read via /api/credentials); otherwise the file-store secret status carries
 *  it. Best-effort: a failed read leaves it false (the section locks, never crashes). */
function useOpenAiKeyPresent(
  apiBaseUrl: string,
  byokEnabled: boolean,
  secrets: SecretStatus[],
): boolean {
  const [byokPresent, setByokPresent] = useState(false);
  useEffect(() => {
    if (!byokEnabled) return;
    const controller = new AbortController();
    void fetchCredentials(apiBaseUrl, controller.signal)
      .then((creds) => {
        if (!controller.signal.aborted) {
          setByokPresent(creds.some((c) => c.provider === "openai" && c.isSet));
        }
      })
      .catch(() => {});
    return () => controller.abort();
  }, [apiBaseUrl, byokEnabled]);
  if (byokEnabled) return byokPresent;
  return secrets.some((s) => s.name === "openai" && s.isSet);
}
