import { NavLink } from "react-router";

import { RailNavItem } from "./RailNavItem";
import { GearIcon } from "./railIcons";
import { MoonIcon, SunIcon } from "./themeIcons";
import { useAuth } from "../../hooks/useAuth";
import type { ThemeProps } from "../../hooks/useTheme";
import { resolveDisplayName } from "../../lib/profile";
import { ROUTES } from "../../lib/routes";
import styles from "./Sidebar.module.css";

interface RailFooterProps extends ThemeProps {
  /** Whether the rail is collapsed to the mini icon rail (labels drop away, actions become icons). */
  collapsed: boolean;
  /** Fired on any nav-link navigation (e.g. so the phone drawer dismisses). */
  onNavigate?: (() => void) | undefined;
}

/** The bottom cluster every product rail ends in: theme, Settings, and the account row (the
 *  signed-in identity, itself the link to the Account page). The only hairline down here is above
 *  the account.
 *
 *  Shared rather than copied because Live grew a rail of its own (journey live-session-lifecycle,
 *  T7) and these three are the same three in both: which product you are standing in changes what
 *  you navigate *to*, never who you are signed in as or how the app is dressed. */
export function RailFooter({ collapsed, theme, onToggleTheme, onNavigate }: RailFooterProps) {
  const { user } = useAuth();
  const displayName = resolveDisplayName(user);
  const goingDark = theme === "light";
  const themeLabel = goingDark ? "Dark theme" : "Light theme";
  const themeAction = `Switch to ${goingDark ? "dark" : "light"} mode`;
  return (
    <>
      <nav className={styles.footer} aria-label="Secondary">
        {collapsed ? (
          <button
            type="button"
            className={styles.railAction}
            onClick={onToggleTheme}
            aria-label={themeAction}
            aria-pressed={theme === "dark"}
            title={themeAction}
          >
            {goingDark ? <SunIcon /> : <MoonIcon />}
          </button>
        ) : (
          <button
            type="button"
            className={styles.navItem}
            onClick={onToggleTheme}
            aria-label={themeAction}
            aria-pressed={theme === "dark"}
          >
            <span className={styles.navIcon} aria-hidden="true">
              {goingDark ? <SunIcon /> : <MoonIcon />}
            </span>
            {themeLabel}
          </button>
        )}
        <RailNavItem
          to={ROUTES.settings}
          icon={<GearIcon />}
          label="Settings"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
      </nav>

      {/* Who is signed in, and the way into the Account page (there is no separate "Account" nav
          entry; this row is it). It carries the house accent spine when the Account surface is
          active, like any other nav destination. */}
      {user &&
        (collapsed ? (
          <NavLink
            to={ROUTES.account}
            onClick={onNavigate}
            className={({ isActive }) =>
              `${styles.railAction} ${isActive ? styles.railActionActive : ""}`.trim()
            }
            aria-label="Your account"
            title={displayName}
          >
            <span className={styles.avatar} aria-hidden="true">
              {displayName.charAt(0)}
            </span>
          </NavLink>
        ) : (
          <NavLink
            to={ROUTES.account}
            onClick={onNavigate}
            className={({ isActive }) =>
              `${styles.account} ${isActive ? styles.accountActive : ""}`.trim()
            }
          >
            <span className={styles.avatar} aria-hidden="true">
              {displayName.charAt(0)}
            </span>
            <span className={styles.accountText}>
              <span className={styles.accountName}>{displayName}</span>
              <span className={styles.accountMeta}>Personal workspace</span>
            </span>
          </NavLink>
        ))}
    </>
  );
}
