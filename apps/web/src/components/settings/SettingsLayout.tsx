import type { ThemePreference } from "../../hooks/useTheme";
import type { SettingsSection } from "../../lib/routes";
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
import { useSettingsSurface } from "./useSettingsSurface";
import styles from "./SettingsLayout.module.css";

interface SettingsLayoutProps {
  apiBaseUrl: string;
  /** The active sub-section (from the `/settings/:section` URL). */
  section: SettingsSection;
  /** The theme preference + setter, threaded through only for the Appearance section. */
  preference: ThemePreference;
  onPreferenceChange: (preference: ThemePreference) => void;
}

/** The Settings surface: a persistent left sub-nav welded to the active section's content. One data
 *  load (see {@link useSettingsSurface}) feeds every section through a shared `SettingsSurface`, so
 *  a key saved in one section flips capabilities and unlocks gated sections everywhere at once.
 *  Sections are URL-addressable (`/settings/:section`) for deep links and Back/Forward. */
export function SettingsLayout({
  apiBaseUrl,
  section,
  preference,
  onPreferenceChange,
}: SettingsLayoutProps) {
  const state = useSettingsSurface(apiBaseUrl);

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
            renderSection(section, state.surface, preference, onPreferenceChange)}
        </div>
      </div>
    </div>
  );
}

/** Pick the section's content for the active sub-nav item. Appearance is the one section driven by
 *  theme state rather than the settings surface. */
function renderSection(
  section: SettingsSection,
  surface: SettingsSurface,
  preference: ThemePreference,
  onPreferenceChange: (preference: ThemePreference) => void,
) {
  switch (section) {
    case "system":
      return <SystemSection surface={surface} />;
    case "appearance":
      return <AppearanceSection preference={preference} onPreferenceChange={onPreferenceChange} />;
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
}
