import { useId } from "react";

import type { ThemePreference } from "../../hooks/useTheme";
import { ComputeSourceSelect } from "../explain/ComputeSourceSelect";
import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { SegmentedControl } from "../primitives/SegmentedControl";
import { CapabilityBadges } from "./CapabilityBadges";
import { ConfigPanel } from "./ConfigPanel";
import { CoverConfigPanel } from "./CoverConfigPanel";
import { CredentialList } from "./CredentialList";
import { TrustedSourcesPanel } from "./TrustedSourcesPanel";
import { VideoConfigPanel } from "./VideoConfigPanel";
import { VoiceConfigPanel } from "./VoiceConfigPanel";
import type { SettingsSurface } from "./settingsSurface";
import styles from "./Settings.module.css";

const isLangsmithKey = (name: string) => name.startsWith("langsmith");
const isModelKey = (name: string) => name.startsWith("model");

/** SYSTEM — the pipeline mode, per-capability providers, the keyless compute fallback, and the
 *  operator/infra keys (Supabase, LangSmith) with LangSmith tracing config. */
export function SystemSection({ surface }: { surface: SettingsSurface }) {
  return (
    <>
      <CollapsibleSection eyebrow="System" title="Runtime" defaultOpen>
        <p className={styles.pipeline}>
          Pipeline mode: <span className="mono">{surface.pipeline}</span>
        </p>
        <CapabilityBadges capabilities={surface.capabilities} />
        {/* Keyless LLM → the user picks where their explanations run (the fallback compute source). */}
        {surface.keyless && <ComputeSourceSelect />}
      </CollapsibleSection>
      <CredentialList
        section="system"
        surface={surface}
        eyebrow="Infrastructure"
        title="Data layer & observability keys"
      />
      <ConfigPanel
        apiBaseUrl={surface.apiBaseUrl}
        perUserConfig={surface.perUserConfigEnabled}
        eyebrow="Observability"
        title="LangSmith tracing"
        filter={isLangsmithKey}
      />
    </>
  );
}

const THEME_SEGMENTS: { value: ThemePreference; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

/** APPEARANCE — the interface theme: Light, Dark, or System (follows the OS preference live). */
export function AppearanceSection({
  preference,
  onPreferenceChange,
}: {
  preference: ThemePreference;
  onPreferenceChange: (preference: ThemePreference) => void;
}) {
  const labelId = useId();
  return (
    <CollapsibleSection eyebrow="Appearance" title="Theme" defaultOpen>
      <div className={styles.field}>
        <span className={styles.label} id={labelId}>
          Interface theme
        </span>
        <SegmentedControl
          segments={THEME_SEGMENTS}
          value={preference}
          onChange={onPreferenceChange}
          aria-labelledby={labelId}
        />
        <p className={styles.hint}>
          {preference === "system"
            ? "Follows your device’s light/dark setting and switches with it automatically."
            : "Pins the interface to this theme on every device."}
        </p>
      </div>
    </CollapsibleSection>
  );
}

/** LLM — the Claude/embeddings keys and the strong/worker model selection. */
export function LlmSection({ surface }: { surface: SettingsSurface }) {
  return (
    <>
      <CredentialList section="llm" surface={surface} eyebrow="LLM" title="Provider keys" />
      <ConfigPanel
        apiBaseUrl={surface.apiBaseUrl}
        perUserConfig={surface.perUserConfigEnabled}
        eyebrow="Models"
        title="Model selection"
        filter={isModelKey}
      />
    </>
  );
}

/** VIDEO — explainer-video generation (narration lives in the Voice section). */
export function VideoSection({ surface }: { surface: SettingsSurface }) {
  return (
    <VideoConfigPanel
      apiBaseUrl={surface.apiBaseUrl}
      keyless={surface.keyless}
      byokEnabled={surface.byokEnabled}
      secrets={surface.secrets}
      keysVersion={surface.keysVersion}
      showVoice={false}
    />
  );
}

/** VOICE — the ElevenLabs key and the narration toggle it gates. */
export function VoiceSection({ surface }: { surface: SettingsSurface }) {
  return (
    <>
      <CredentialList section="voice" surface={surface} eyebrow="Voice" title="Provider key" />
      <VoiceConfigPanel
        apiBaseUrl={surface.apiBaseUrl}
        byokEnabled={surface.byokEnabled}
        secrets={surface.secrets}
        keysVersion={surface.keysVersion}
      />
    </>
  );
}

/** TOOLS — image generation (covers), plus the YouTube and web-search keys. */
export function ToolsSection({ surface }: { surface: SettingsSurface }) {
  return (
    <>
      <CredentialList section="tools" surface={surface} eyebrow="Tools" title="Service keys" />
      <CoverConfigPanel
        apiBaseUrl={surface.apiBaseUrl}
        byokEnabled={surface.byokEnabled}
        secrets={surface.secrets}
        keysVersion={surface.keysVersion}
      />
    </>
  );
}

/** SOURCES — the grounding source-authority allow/deny configuration. */
export function SourcesSection({ surface }: { surface: SettingsSurface }) {
  return <TrustedSourcesPanel apiBaseUrl={surface.apiBaseUrl} />;
}
