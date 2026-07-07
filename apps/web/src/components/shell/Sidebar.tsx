import type { ReactNode } from "react";
import { NavLink } from "react-router";

import { Button } from "../primitives/Button";
import { BrandMark } from "./BrandMark";
import { RunList } from "./RunList";
import { SidebarToggle } from "./SidebarToggle";
import { ThemeToggle } from "./ThemeToggle";
import { useAuth } from "../../hooks/useAuth";
import type { RunsState } from "../../hooks/useRuns";
import type { ThemeProps } from "../../hooks/useTheme";
import type { CourseRun } from "../../types/course";
import styles from "./Sidebar.module.css";

interface SidebarProps extends ThemeProps {
  runs: RunsState;
  onReloadRuns: () => void;
  onNewCourse: () => void;
  /** Show the "Admin Portal" nav entry — only for admins. */
  showAdmin?: boolean;
  /** Whether the rail is collapsed to the mini icon rail (run history hidden, actions as icons). */
  collapsed: boolean;
  /** Collapse / expand the rail — the toggle lives in the brand row in both states. */
  onToggleCollapse: () => void;
  /** Fired on any nav-link navigation (e.g. so the phone drawer dismisses). */
  onNavigate?: (() => void) | undefined;
  onSelectRun?: ((run: CourseRun) => void) | undefined;
  onDeleteRun?: ((run: CourseRun) => void) | undefined;
  onCancelRun?: ((run: CourseRun) => void) | undefined;
  cancellingRunId?: string | null | undefined;
  selectedRunId?: string | undefined;
}

/** The instrument rail: brand, the primary "New course" action, the app's primary nav (Home /
 *  My courses / Activity / Bookmarks — real links, spine-marked when active), the run-history
 *  feed, and the Settings/Admin nav — hairline-divided regions, not floating cards. Collapses to
 *  a mini icon rail: labels drop away leaving the icons; the run history is hidden until
 *  expanded. The toggle stays mounted across the transition so keyboard focus persists. */
export function Sidebar({
  runs,
  onReloadRuns,
  onNewCourse,
  showAdmin,
  collapsed,
  onToggleCollapse,
  onNavigate,
  onSelectRun,
  onDeleteRun,
  onCancelRun,
  cancellingRunId,
  selectedRunId,
  theme,
  onToggleTheme,
}: SidebarProps) {
  const { user, signOut } = useAuth();
  return (
    <div className={styles.sidebar} data-collapsed={collapsed || undefined}>
      <div className={styles.brand}>
        {!collapsed && <BrandMark size={24} />}
        {!collapsed && <span className={styles.wordmark}>Lunaris</span>}
        <SidebarToggle collapsed={collapsed} onClick={onToggleCollapse} />
      </div>

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
          <Button variant="primary" className={styles.newCourse} onClick={onNewCourse}>
            New course
          </Button>
        )}
      </div>

      <nav className={styles.primaryNav} aria-label="Primary">
        <NavItem to="/" end icon={<HomeIcon />} label="Home" {...{ collapsed, onNavigate }} />
        <NavItem
          to="/courses"
          icon={<GridIcon />}
          label="My courses"
          {...{ collapsed, onNavigate }}
        />
        <NavItem
          to="/activity"
          icon={<ActivityIcon />}
          label="Activity"
          {...{ collapsed, onNavigate }}
        />
        <NavItem
          to="/bookmarks"
          icon={<BookmarkIcon />}
          label="Bookmarks"
          {...{ collapsed, onNavigate }}
        />
      </nav>

      {!collapsed && (
        <nav className={styles.history} aria-label="Run history">
          <span className={`eyebrow ${styles.sectionLabel}`}>Recent runs</span>
          <RunList
            state={runs}
            onRetry={onReloadRuns}
            onSelectRun={onSelectRun}
            onDeleteRun={onDeleteRun}
            onCancelRun={onCancelRun}
            cancellingRunId={cancellingRunId}
            selectedRunId={selectedRunId}
          />
        </nav>
      )}

      {user && !collapsed && (
        <div className={styles.account}>
          <span className={styles.avatar} aria-hidden="true">
            {(user.email ?? "?").charAt(0)}
          </span>
          <span className={styles.accountEmail} title={user.email ?? undefined}>
            {user.email}
          </span>
          <button
            type="button"
            className={styles.railAction}
            onClick={() => void signOut()}
            aria-label={`Sign out ${user.email ?? ""}`.trim()}
            title="Sign out"
          >
            <SignOutIcon />
          </button>
        </div>
      )}

      <div className={styles.footer}>
        {showAdmin && (
          <NavItem
            to="/admin"
            icon={<AdminIcon />}
            label="Admin Portal"
            {...{ collapsed, onNavigate }}
          />
        )}
        <NavItem
          to="/settings"
          icon={<GearIcon />}
          label="Settings"
          {...{ collapsed, onNavigate }}
        />
        {user && collapsed && (
          <button
            type="button"
            className={styles.railAction}
            onClick={() => void signOut()}
            aria-label={`Sign out ${user.email ?? ""}`.trim()}
            title="Sign out"
          >
            <SignOutIcon />
          </button>
        )}
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>
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

function SignOutIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M6 14H3.5A1.5 1.5 0 0 1 2 12.5v-9A1.5 1.5 0 0 1 3.5 2H6M10.5 11l3-3-3-3M13 8H6"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
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

function AdminIcon() {
  // A shield with a check — the admin / privileged-access mark.
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M8 1.75 13 3.5v4.2c0 3.2-2.1 5.3-5 6.3-2.9-1-5-3.1-5-6.3V3.5L8 1.75Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path
        d="M5.9 7.9 7.4 9.4 10.2 6.4"
        stroke="currentColor"
        strokeWidth="1.4"
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
