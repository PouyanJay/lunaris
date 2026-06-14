import { useEffect, useId, useMemo, useState } from "react";

import { useConfig } from "../../hooks/useConfig";
import { useConfigSaver, type SaveFeedback } from "../../hooks/useConfigSaver";
import { fetchCredentials } from "../../lib/credentials";
import {
  VIDEO_LENGTH_KEYS,
  VIDEO_MASTER_KEY,
  VIDEO_VOICE_KEY,
  boolToConfigValue,
  type ConfigSetting,
} from "../../lib/config";
import type { SecretStatus } from "../../lib/settings";
import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { Switch } from "../primitives/Switch";
import { SaveResult } from "./SaveResult";
import styles from "./Config.module.css";

interface VideoConfigPanelProps {
  apiBaseUrl: string;
  /** Whether this account runs the LLM on its keyless fallback. Video is keyed-only (a draft-tier
   *  model can't write Manim and Gate B needs vision), so the whole section is then deactivated. */
  keyless: boolean;
  /** Whether per-user BYOK is on — decides where the ElevenLabs key status is read from. */
  byokEnabled: boolean;
  /** The file-store secret statuses (the non-BYOK path's source for the ElevenLabs key). */
  secrets: SecretStatus[];
}

const LABELS: Record<string, string> = {
  videoEnabled: "Generate videos",
  videoVoice: "Narrate videos",
  videoSummarySeconds: "Course trailer length",
  videoOverviewSeconds: "Topic intro length",
  videoLessonSeconds: "Lesson video length",
};

const DESCRIPTIONS: Record<string, string> = {
  videoEnabled:
    "Add an animated explainer to each lesson, plus a course trailer and topic intro.",
  videoVoice:
    "Narrate in one pass with ElevenLabs. Off renders silent and voice-ready — you can add narration later.",
};

// Length presets per kind (seconds), all within the backend's 15–600s bound. The trailer + lesson
// sit in the validated 60–90s envelope; the chaptered topic intro runs longer.
const LENGTH_PRESETS: Record<string, number[]> = {
  videoSummarySeconds: [60, 75, 90],
  videoOverviewSeconds: [120, 180, 240, 300],
  videoLessonSeconds: [60, 75, 90],
};

/** The Video section of Settings (explainer-video V6): a three-layer disclosure — master toggle →
 *  (when on) the voice toggle + the three per-kind lengths. The voice toggle requires a validated
 *  ElevenLabs key. Keyless accounts see the whole section deactivated with a "needs a key"
 *  affordance, since video generation is a keyed-only capability. */
export function VideoConfigPanel({
  apiBaseUrl,
  keyless,
  byokEnabled,
  secrets,
}: VideoConfigPanelProps) {
  const { state, apply } = useConfig(apiBaseUrl);
  const { save, busy, feedback } = useConfigSaver(apiBaseUrl, apply);
  const voiceKeyPresent = useElevenLabsKeyPresent(apiBaseUrl, byokEnabled, secrets);

  const byName = useMemo(
    () =>
      state.status === "ready"
        ? new Map(state.settings.map((setting) => [setting.name, setting]))
        : new Map<string, ConfigSetting>(),
    [state],
  );
  const master = byName.get(VIDEO_MASTER_KEY);
  const masterOn = master?.value === "true";
  const voice = byName.get(VIDEO_VOICE_KEY);

  return (
    <CollapsibleSection eyebrow="Video" title="Video generation" defaultOpen={false}>
      <p className={styles.muted}>
        Generated explainer videos in your courses — a trailer and topic intro up top, and a video
        at the head of each lesson.
      </p>

      {state.status === "loading" && <p className={styles.muted}>Loading configuration…</p>}
      {state.status === "error" && (
        <div className={styles.stateBlock} role="alert">
          <p className={styles.error}>{state.message}</p>
        </div>
      )}

      {state.status === "ready" && master && (
        <div className={styles.rows}>
          {keyless ? (
            <KeylessVideoNotice master={master} />
          ) : (
            <>
              <ToggleRow
                setting={master}
                busy={busy[master.name] ?? false}
                feedback={feedback[master.name]}
                onToggle={(on) => save(master.name, boolToConfigValue(on))}
              />
              {masterOn && (
                <>
                  {voice && (
                    <VoiceRow
                      setting={voice}
                      keyPresent={voiceKeyPresent}
                      busy={busy[VIDEO_VOICE_KEY] ?? false}
                      feedback={feedback[VIDEO_VOICE_KEY]}
                      onToggle={(on) => save(VIDEO_VOICE_KEY, boolToConfigValue(on))}
                    />
                  )}
                  {VIDEO_LENGTH_KEYS.map((key) => {
                    const setting = byName.get(key);
                    return setting ? (
                      <LengthRow
                        key={key}
                        setting={setting}
                        busy={busy[key] ?? false}
                        feedback={feedback[key]}
                        onSave={(value) => save(key, value)}
                      />
                    ) : null;
                  })}
                </>
              )}
            </>
          )}
        </div>
      )}
    </CollapsibleSection>
  );
}

/** Keyless tier: the master toggle is shown locked OFF with the standard needs-a-key affordance. */
function KeylessVideoNotice({ master }: { master: ConfigSetting }) {
  const controlId = useId();
  const labelId = `${controlId}-label`;
  return (
    <div className={styles.row}>
      <div className={styles.head}>
        <span className={styles.label} id={labelId}>
          {LABELS[master.name]}
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
        Video generation needs an Anthropic API key — add one in Keys above. It is a keyed-only
        feature: a draft-tier model can&rsquo;t render videos.
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
  const description = DESCRIPTIONS[setting.name];
  return (
    <div className={styles.row}>
      <div className={styles.head}>
        <label className={styles.label} htmlFor={controlId} id={labelId}>
          {LABELS[setting.name]}
        </label>
        <Switch
          id={controlId}
          checked={setting.value === "true"}
          disabled={busy}
          aria-labelledby={labelId}
          {...(description ? { "aria-describedby": hintId } : {})}
          onChange={onToggle}
        />
      </div>
      {description && (
        <p id={hintId} className={styles.hint}>
          {description}
        </p>
      )}
      <SaveResult feedback={feedback} />
    </div>
  );
}

interface VoiceRowProps {
  setting: ConfigSetting;
  keyPresent: boolean;
  busy: boolean;
  feedback: SaveFeedback | undefined;
  onToggle: (on: boolean) => void;
}

/** The narration toggle — shown off and disabled until a validated ElevenLabs key exists ("the
 *  voice toggle cannot be on without a validated key"). The locked hint below guides the fix. */
function VoiceRow({ setting, keyPresent, busy, feedback, onToggle }: VoiceRowProps) {
  const controlId = useId();
  const hintId = useId();
  const labelId = `${controlId}-label`;
  return (
    <div className={styles.row}>
      <div className={styles.head}>
        <label className={styles.label} htmlFor={controlId} id={labelId}>
          {LABELS[setting.name]}
        </label>
        <Switch
          id={controlId}
          // Without a key narration is impossible, so the toggle reads off and locked regardless of
          // the stored intent — turning it back on unlocks once a key is added.
          checked={keyPresent && setting.value === "true"}
          disabled={busy || !keyPresent}
          aria-labelledby={labelId}
          aria-describedby={hintId}
          onChange={onToggle}
        />
      </div>
      <p id={hintId} className={styles.hint}>
        {keyPresent
          ? DESCRIPTIONS.videoVoice
          : "Add an ElevenLabs API key in Keys above to narrate. Without one, videos render silent — voice-ready, so you can add narration later."}
      </p>
      <SaveResult feedback={feedback} />
    </div>
  );
}

interface LengthRowProps {
  setting: ConfigSetting;
  busy: boolean;
  feedback: SaveFeedback | undefined;
  onSave: (value: string) => void;
}

function LengthRow({ setting, busy, feedback, onSave }: LengthRowProps) {
  const controlId = useId();
  const labelId = `${controlId}-label`;
  const presets = LENGTH_PRESETS[setting.name] ?? [];
  // Include the stored value so a non-preset length (operator default / earlier choice) still shows.
  const options = [...new Set<number>([...presets, Number(setting.value)])]
    .filter((n) => Number.isFinite(n) && n > 0)
    .sort((a, b) => a - b);
  return (
    <div className={styles.row}>
      <div className={styles.head}>
        <label className={styles.label} htmlFor={controlId} id={labelId}>
          {LABELS[setting.name]}
        </label>
        <select
          id={controlId}
          className={styles.lengthSelect}
          value={setting.value}
          disabled={busy}
          aria-labelledby={labelId}
          onChange={(event) => onSave(event.target.value)}
        >
          {options.map((seconds) => (
            <option key={seconds} value={String(seconds)}>
              {formatSeconds(seconds)}
            </option>
          ))}
        </select>
      </div>
      <SaveResult feedback={feedback} />
    </div>
  );
}

/** A whole number of seconds as m:ss (75 → "1:15") — the natural reading for a clip length. */
function formatSeconds(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

/** Whether the caller has a validated ElevenLabs key — the gate for the voice toggle. Under BYOK
 *  the per-user key lives in the vault (read via /api/credentials); otherwise the file-store secret
 *  status carries it. Best-effort: a failed read leaves it false (the toggle locks, never crashes). */
function useElevenLabsKeyPresent(
  apiBaseUrl: string,
  byokEnabled: boolean,
  secrets: SecretStatus[],
): boolean {
  const [byokPresent, setByokPresent] = useState(false);
  useEffect(() => {
    if (!byokEnabled) return;
    const controller = new AbortController();
    fetchCredentials(apiBaseUrl, controller.signal)
      .then((creds) => setByokPresent(creds.some((c) => c.provider === "elevenlabs" && c.isSet)))
      .catch(() => {
        /* best-effort: leave false so the toggle locks with the add-a-key hint */
      });
    return () => controller.abort();
  }, [apiBaseUrl, byokEnabled]);
  if (byokEnabled) return byokPresent;
  return secrets.some((s) => s.name === "elevenlabs" && s.isSet);
}
