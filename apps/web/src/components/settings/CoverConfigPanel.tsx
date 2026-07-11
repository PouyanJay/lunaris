import { useId, useMemo } from "react";

import { useConfig } from "../../hooks/useConfig";
import { useConfigSaver, type SaveFeedback } from "../../hooks/useConfigSaver";
import { useProviderKeyPresent } from "../../hooks/useProviderKeyPresent";
import {
  COVER_MASTER_KEY,
  COVER_PRESET_KEY,
  COVER_STYLE_PRESETS,
  boolToConfigValue,
  type ConfigSetting,
} from "../../lib/config";
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
  /** Bumped by the Settings shell whenever a key is saved/removed, so a freshly-added OpenAI key
   *  unlocks this section immediately instead of only after a full page reload. */
  keysVersion?: number;
}

const PRESET_LABELS: Record<string, string> = {
  general: "General — premium enterprise infographic (default)",
  nocturne: "Nocturne — night-sky editorial",
  blueprint: "Blueprint — technical line-art",
  aurora: "Aurora — soft abstract gradient",
};

/** The Cover section of Settings (course-cover-images T10): a master toggle for auto-generating an
 *  AI cover at build time, and — when on — the art-direction preset. AI covers need an OpenAI key
 *  (GPT Image 2), so without one the section is deactivated with a needs-a-key affordance and the
 *  account shows the Typographic cover instead. */
export function CoverConfigPanel({
  apiBaseUrl,
  byokEnabled,
  secrets,
  keysVersion = 0,
}: CoverConfigPanelProps) {
  const { state, apply } = useConfig(apiBaseUrl);
  const { save, busy, feedback } = useConfigSaver(apiBaseUrl, apply);
  const keyPresent = useProviderKeyPresent(
    apiBaseUrl,
    byokEnabled,
    secrets,
    "openai",
    keysVersion,
  );

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
        AI cover images need an OpenAI API key. Paste one into the &ldquo;OpenAI API key&rdquo;
        field in Keys &amp; configuration above and press Save — this toggle unlocks immediately.
        Without a key, courses show a Typographic cover.
        {master.default === "true" ? " (On by default once keyed.)" : ""}
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

