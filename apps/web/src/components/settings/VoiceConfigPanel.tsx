import { useId, useMemo } from "react";

import { useConfig } from "../../hooks/useConfig";
import { useConfigSaver } from "../../hooks/useConfigSaver";
import { useProviderKeyPresent } from "../../hooks/useProviderKeyPresent";
import { VIDEO_VOICE_KEY, boolToConfigValue, type ConfigSetting } from "../../lib/config";
import type { SecretStatus } from "../../lib/settings";
import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { Switch } from "../primitives/Switch";
import { SaveResult } from "./SaveResult";
import styles from "./Config.module.css";

interface VoiceConfigPanelProps {
  apiBaseUrl: string;
  /** Per-user BYOK on → the ElevenLabs key status comes from the vault; off → the file-store secrets. */
  byokEnabled: boolean;
  secrets: SecretStatus[];
  /** Bumped by the Settings shell on every key change, so a freshly-added ElevenLabs key unlocks the
   *  narrate toggle at once instead of only after a reload. */
  keysVersion?: number;
}

/** The Voice section's narration control (relocated from the Video section). Narration is one pass
 *  with ElevenLabs, so the toggle stays off and locked until a validated ElevenLabs key exists — the
 *  key itself is set just above this, in the same Voice section. It writes the same `videoVoice`
 *  config the Video pipeline reads, so behavior is unchanged; only its home moved. */
export function VoiceConfigPanel({
  apiBaseUrl,
  byokEnabled,
  secrets,
  keysVersion = 0,
}: VoiceConfigPanelProps) {
  const { state, apply } = useConfig(apiBaseUrl);
  const { save, busy, feedback } = useConfigSaver(apiBaseUrl, apply);
  const keyPresent = useProviderKeyPresent(
    apiBaseUrl,
    byokEnabled,
    secrets,
    "elevenlabs",
    keysVersion,
  );

  const voice = useMemo<ConfigSetting | undefined>(
    () =>
      state.status === "ready"
        ? state.settings.find((setting) => setting.name === VIDEO_VOICE_KEY)
        : undefined,
    [state],
  );

  const controlId = useId();
  const hintId = useId();
  const labelId = `${controlId}-label`;

  return (
    <CollapsibleSection eyebrow="Voice" title="Narration" defaultOpen={false}>
      <p className={styles.muted}>
        Narrate explainer videos in one pass with ElevenLabs. Off renders them silent and
        voice-ready — you can add narration later.
      </p>

      {state.status === "loading" && <p className={styles.muted}>Loading configuration…</p>}
      {state.status === "error" && (
        <div className={styles.stateBlock} role="alert">
          <p className={styles.error}>{state.message}</p>
        </div>
      )}

      {state.status === "ready" && voice && (
        <div className={styles.rows}>
          <div className={styles.row}>
            <div className={styles.head}>
              <label className={styles.label} htmlFor={controlId} id={labelId}>
                Narrate videos
              </label>
              <Switch
                id={controlId}
                // Without a key narration is impossible, so the toggle reads off and locked
                // regardless of the stored intent; it unlocks the moment a key is added above.
                checked={keyPresent && voice.value === "true"}
                disabled={(busy[VIDEO_VOICE_KEY] ?? false) || !keyPresent}
                aria-labelledby={labelId}
                aria-describedby={hintId}
                onChange={(on) => save(VIDEO_VOICE_KEY, boolToConfigValue(on))}
              />
            </div>
            <p id={hintId} className={styles.hint}>
              {keyPresent
                ? "Narrate in one pass with ElevenLabs. Off renders silent and voice-ready — you can add narration later."
                : "Add an ElevenLabs API key above to narrate. Without one, videos render silent — voice-ready, so you can add narration later."}
            </p>
            <SaveResult feedback={feedback[VIDEO_VOICE_KEY]} />
          </div>
        </div>
      )}
    </CollapsibleSection>
  );
}
