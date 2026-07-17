import { Link } from "react-router";

import { ACCOUNT_SECTIONS, accountPath, type AccountSection } from "../../lib/routes";
import styles from "../settings/SettingsLayout.module.css";

const SECTION_LABELS: Record<AccountSection, string> = {
  "user-account": "User account",
  "admin-portal": "Admin Portal",
};

/** The Account sub-nav — shown only to admins (the one place with more than the user's own account):
 *  User account and Admin Portal, as real deep links, the active one spine-marked. Reuses the
 *  Settings sub-nav chrome so the two surfaces read as one system. */
export function AccountNav({ active }: { active: AccountSection }) {
  return (
    <nav className={styles.nav} aria-label="Account sections">
      <ul className={styles.navList}>
        {ACCOUNT_SECTIONS.map((section) => {
          const current = section === active;
          return (
            <li key={section}>
              <Link
                to={accountPath(section)}
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
