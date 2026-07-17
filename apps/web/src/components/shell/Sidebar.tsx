import type { ReactNode } from "react";
import { NavLink } from "react-router";

import { Button } from "../primitives/Button";
import { MoonIcon, SunIcon } from "./themeIcons";
import { useAuth } from "../../hooks/useAuth";
import type { ThemeProps } from "../../hooks/useTheme";
import { ROUTES } from "../../lib/routes";
import { resolveDisplayName } from "../../lib/profile";
import styles from "./Sidebar.module.css";

interface SidebarProps extends ThemeProps {
  onNewCourse: () => void;
  /** Whether the rail is collapsed to the mini icon rail (labels drop away, actions become icons). */
  collapsed: boolean;
  /** Fired on any nav-link navigation (e.g. so the phone drawer dismisses). */
  onNavigate?: (() => void) | undefined;
}

/** The instrument rail: the "New course" action, the app's primary nav (Home / My courses /
 *  Activity / Bookmarks — real links, spine-marked when active), and a bottom cluster — theme,
 *  Settings, and the account row (a link to the Account page). Hairline-divided regions, not
 *  floating cards: the only rule down here is above the account. Collapses to a mini icon rail:
 *  labels drop away leaving the icons. The brand and the collapse toggle live in the top bar above
 *  the rail (see AgentShell), so the rail leads straight with its primary action. */
export function Sidebar({
  onNewCourse,
  collapsed,
  onNavigate,
  theme,
  onToggleTheme,
}: SidebarProps) {
  const { user } = useAuth();
  const displayName = resolveDisplayName(user);
  const goingDark = theme === "light";
  const themeLabel = goingDark ? "Dark theme" : "Light theme";
  const themeAction = `Switch to ${goingDark ? "dark" : "light"} mode`;
  return (
    <div className={styles.sidebar} data-collapsed={collapsed || undefined}>
      <div className={styles.actions}>
        {collapsed ? (
          <button
            type="button"
            className={styles.railAction}
            onClick={onNewCourse}
            aria-label="New course"
            title="New course"
          >
            <PlusIcon />
          </button>
        ) : (
          <Button variant="secondary" className={styles.newCourse} onClick={onNewCourse}>
            <PlusIcon />
            New course
          </Button>
        )}
      </div>

      <nav className={styles.primaryNav} aria-label="Primary">
        <NavItem
          to={ROUTES.home}
          end
          icon={<HomeIcon />}
          label="Home"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
        <NavItem
          to={ROUTES.library}
          icon={<GridIcon />}
          label="My courses"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
        <NavItem
          to={ROUTES.activity}
          icon={<ActivityIcon />}
          label="Activity"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
        <NavItem
          to={ROUTES.bookmarks}
          icon={<BookmarkIcon />}
          label="Bookmarks"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
      </nav>

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
        <NavItem
          to={ROUTES.settings}
          icon={<GearIcon />}
          label="Settings"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
        <NavItem
          to={ROUTES.account}
          icon={<AccountIcon />}
          label="Account"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
      </nav>

      {/* The identity row at the foot of the rail — who's signed in, and a shortcut to the Account
          page. The active marker lives on the labeled "Account" nav entry above, so this row never
          carries the accent spine (two selected rows would read as a bug). */}
      {user &&
        (collapsed ? (
          <NavLink
            to={ROUTES.account}
            onClick={onNavigate}
            className={() => styles.railAction}
            aria-label="Your account"
            title={displayName}
          >
            <span className={styles.avatar} aria-hidden="true">
              {displayName.charAt(0)}
            </span>
          </NavLink>
        ) : (
          <NavLink to={ROUTES.account} onClick={onNavigate} className={() => styles.account}>
            <span className={styles.avatar} aria-hidden="true">
              {displayName.charAt(0)}
            </span>
            <span className={styles.accountText}>
              <span className={styles.accountName}>{displayName}</span>
              <span className={styles.accountMeta}>Personal workspace</span>
            </span>
          </NavLink>
        ))}
    </div>
  );
}

/** One primary-nav destination: a real link (NavLink sets aria-current="page" when active), the
 *  house 2px accent spine marking the active entry. Collapsed = icon-only with a tooltip name. */
function NavItem({
  to,
  end,
  icon,
  label,
  collapsed,
  onNavigate,
}: {
  to: string;
  end?: boolean;
  icon: ReactNode;
  label: string;
  collapsed: boolean;
  onNavigate?: (() => void) | undefined;
}) {
  if (collapsed) {
    return (
      <NavLink
        to={to}
        end={end ?? false}
        onClick={onNavigate}
        className={({ isActive }) =>
          `${styles.railAction} ${isActive ? styles.railActionActive : ""}`.trim()
        }
        aria-label={label}
        title={label}
      >
        {icon}
      </NavLink>
    );
  }
  return (
    <NavLink
      to={to}
      end={end ?? false}
      onClick={onNavigate}
      className={({ isActive }) =>
        `${styles.navItem} ${isActive ? styles.navItemActive : ""}`.trim()
      }
    >
      <span className={styles.navIcon} aria-hidden="true">
        {icon}
      </span>
      {label}
    </NavLink>
  );
}

function HomeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 10.5 12 3l9 7.5M5 9.5V20h14V9.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function GridIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3.75 3.75h6.5v6.5h-6.5zM13.75 3.75h6.5v6.5h-6.5zM3.75 13.75h6.5v6.5h-6.5zM13.75 13.75h6.5v6.5h-6.5z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ActivityIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 12h4l2 6 4-14 2 8h6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function BookmarkIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6 3h12v18l-6-4-6 4z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M8 3.25v9.5M3.25 8h9.5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

function AccountIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 12.75a3.75 3.75 0 1 0 0-7.5 3.75 3.75 0 0 0 0 7.5ZM4.5 19.5a7.5 7.5 0 0 1 15 0"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.24-.438.613-.43.992a7.7 7.7 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.5 6.5 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.5 6.5 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.9 6.9 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
