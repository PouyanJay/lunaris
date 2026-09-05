import { Link } from "react-router";

import { ButtonLink } from "../primitives/ButtonLink";
import { RailFooter } from "../shell/RailFooter";
import { RailNavItem } from "../shell/RailNavItem";
import { SidebarToggle } from "../shell/SidebarToggle";
import { PlusIcon } from "../shell/railIcons";
import type { ThemeProps } from "../../hooks/useTheme";
import { LIVE_SESSIONS_PATH } from "./liveRoutes";
import styles from "../shell/Sidebar.module.css";

/** Where the composer opens already in Live mode, so the rail's primary action does not send a
 *  learner out of the product they are standing in. */
const NEW_SESSION_PATH = "/new?mode=live";

interface LiveRailProps extends ThemeProps {
  /** Whether the rail is collapsed to the mini icon rail (labels drop away, actions become icons). */
  collapsed: boolean;
  /** Collapse / expand the rail — the toggle rides the rail it controls. */
  onToggleCollapsed: () => void;
}

/** Live's instrument rail (journey live-session-lifecycle, T7).
 *
 *  Live shipped through Phase 2 with a brand-only top bar and nothing else: no nav, no settings,
 *  and no way back to Studio short of editing the URL. This is the same rail Studio has, wearing
 *  Live's own destinations.
 *
 *  It shares the parts that are genuinely the same — {@link RailNavItem}, {@link RailFooter}, the
 *  stylesheet — rather than copying them, because which product you are standing in changes what
 *  you navigate *to* and nothing about who you are signed in as or how the app is dressed.
 *
 *  Studio's own nouns are deliberately absent. "My courses", "Activity" and "Bookmarks" are about
 *  artifacts a factory built; a session is not one of those, and a nav entry that goes somewhere
 *  irrelevant is worse than no nav entry. */
export function LiveRail({ collapsed, onToggleCollapsed, theme, onToggleTheme }: LiveRailProps) {
  return (
    <div className={styles.sidebar} data-collapsed={collapsed || undefined}>
      {/* The primary-action row, in Studio's shape: the action fills it and the collapse toggle
          sits at its right end. A link rather than a button, because it goes somewhere — so
          Cmd-click and "open in new tab" work, as they do for every other destination here. */}
      <div className={styles.actions}>
        {collapsed ? (
          <Link
            to={NEW_SESSION_PATH}
            className={styles.railAction}
            aria-label="New session"
            title="New session"
          >
            <PlusIcon />
          </Link>
        ) : (
          <ButtonLink to={NEW_SESSION_PATH} variant="secondary" className={styles.newCourse}>
            <PlusIcon />
            New session
          </ButtonLink>
        )}
        <SidebarToggle collapsed={collapsed} onClick={onToggleCollapsed} />
      </div>

      <nav className={styles.primaryNav} aria-label="Primary">
        <RailNavItem
          to={LIVE_SESSIONS_PATH}
          icon={<HistoryIcon />}
          label="Your sessions"
          collapsed={collapsed}
        />
        <RailNavItem to="/" icon={<StudioIcon />} label="Studio" collapsed={collapsed} />
      </nav>

      <RailFooter collapsed={collapsed} theme={theme} onToggleTheme={onToggleTheme} />
    </div>
  );
}

/** A clock turned back: the sessions you have had, newest first. */
function HistoryIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1M3.5 4.5V10h5.5M12 7.5V12l3 2"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** The other product: a stack of built artifacts, which is what Studio makes and Live does not. */
function StudioIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3.5 20.5 8 12 12.5 3.5 8zM3.5 12l8.5 4.5 8.5-4.5M3.5 16l8.5 4.5 8.5-4.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
