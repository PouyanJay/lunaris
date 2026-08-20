import { Button } from "../primitives/Button";
import { RailFooter } from "./RailFooter";
import { RailNavItem } from "./RailNavItem";
import { SidebarToggle } from "./SidebarToggle";
import { PlusIcon } from "./railIcons";
import type { ThemeProps } from "../../hooks/useTheme";
import { ROUTES } from "../../lib/routes";
import styles from "./Sidebar.module.css";

interface SidebarProps extends ThemeProps {
  onNewCourse: () => void;
  /** Whether the rail is collapsed to the mini icon rail (labels drop away, actions become icons). */
  collapsed: boolean;
  /** Collapse / expand the rail — the toggle lives at the head of the rail itself. */
  onToggleCollapsed: () => void;
  /** Fired on any nav-link navigation (e.g. so the phone drawer dismisses). */
  onNavigate?: (() => void) | undefined;
  /** Warm the My-courses library on hover/focus of its nav entry, so the click lands on ready
   *  data (library-instant-covers). */
  onPrefetchLibrary?: (() => void) | undefined;
}

/** The instrument rail: a primary-action row ("New course" with the collapse toggle at its right
 *  end), the app's primary nav (Home / My courses / Activity / Bookmarks — real links, spine-marked
 *  when active), and a bottom cluster — theme, Settings, and the account row (the signed-in identity,
 *  itself the link to the Account page). Hairline-divided regions, not floating cards: the only rule
 *  down here is above the account. Collapses to a mini icon rail: labels drop away leaving the icons,
 *  and the action row stacks (toggle over New course). The brand lives in the top bar above the rail
 *  (see AgentShell); the collapse toggle rides the rail it controls. */
export function Sidebar({
  onNewCourse,
  collapsed,
  onToggleCollapsed,
  onNavigate,
  onPrefetchLibrary,
  theme,
  onToggleTheme,
}: SidebarProps) {
  return (
    <div className={styles.sidebar} data-collapsed={collapsed || undefined}>
      {/* The primary-action row: "New course" grows to fill it and the collapse toggle sits at its
          right end, so the top row carries real content — no empty band. Collapsed, the row becomes a
          centred column with the toggle above the New-course icon (see the CSS), keeping an
          always-visible affordance to grow the rail back. */}
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
        <SidebarToggle collapsed={collapsed} onClick={onToggleCollapsed} />
      </div>

      <nav className={styles.primaryNav} aria-label="Primary">
        <RailNavItem
          to={ROUTES.home}
          end
          icon={<HomeIcon />}
          label="Home"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
        <RailNavItem
          to={ROUTES.library}
          icon={<GridIcon />}
          label="My courses"
          collapsed={collapsed}
          onNavigate={onNavigate}
          onPrefetch={onPrefetchLibrary}
        />
        <RailNavItem
          to={ROUTES.activity}
          icon={<ActivityIcon />}
          label="Activity"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
        <RailNavItem
          to={ROUTES.bookmarks}
          icon={<BookmarkIcon />}
          label="Bookmarks"
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
      </nav>

      <RailFooter
        collapsed={collapsed}
        theme={theme}
        onToggleTheme={onToggleTheme}
        onNavigate={onNavigate}
      />
    </div>
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
