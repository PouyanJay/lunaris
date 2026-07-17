import { Link } from "react-router";

import { SETTINGS_SECTIONS, settingsPath, type SettingsSection } from "../../lib/routes";
import styles from "./SettingsLayout.module.css";

/** The human label for each section, in nav order. */
const SECTION_LABELS: Record<SettingsSection, string> = {
  system: "System",
  appearance: "Appearance",
  llm: "LLM",
  video: "Video",
  voice: "Voice",
  tools: "Tools",
  sources: "Sources",
};

/** The Settings sub-nav: the 7 sections as real links (deep-linkable `/settings/:section`), the
 *  active one spine-marked. A `<nav>` list so it's keyboard-navigable and announced as navigation.
 *  The route's resolved `active` section — not the router's own match — is the single source of
 *  truth for the active marking (`aria-current="page"` + the spine), so it's correct the instant the
 *  route changes. A plain `Link` (not `NavLink`) is used precisely so that our `aria-current` wins. */
export function SettingsNav({ active }: { active: SettingsSection }) {
  return (
    <nav className={styles.nav} aria-label="Settings sections">
      <ul className={styles.navList}>
        {SETTINGS_SECTIONS.map((section) => {
          const current = section === active;
          return (
            <li key={section}>
              <Link
                to={settingsPath(section)}
                aria-current={current ? "page" : undefined}
                className={`${styles.navItem} ${current ? styles.navItemActive : ""}`.trim()}
              >
                {SECTION_LABELS[section]}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
