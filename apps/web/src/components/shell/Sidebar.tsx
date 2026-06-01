import { Button } from "../primitives/Button";
import { BrandMark } from "./BrandMark";
import { RunList } from "./RunList";
import { SidebarToggle } from "./SidebarToggle";
import type { RunsState } from "../../hooks/useRuns";
import type { CourseRun } from "../../types/course";
import styles from "./Sidebar.module.css";

interface SidebarProps {
  runs: RunsState;
  onReloadRuns: () => void;
  onNewCourse: () => void;
  onOpenSettings: () => void;
  settingsActive: boolean;
  /** Whether the rail is collapsed to the mini icon rail (run history hidden, actions as icons). */
  collapsed: boolean;
  /** Collapse / expand the rail — the toggle lives in the brand row in both states. */
  onToggleCollapse: () => void;
  onSelectRun?: ((run: CourseRun) => void) | undefined;
  onDeleteRun?: ((run: CourseRun) => void) | undefined;
  onCancelRun?: ((run: CourseRun) => void) | undefined;
  cancellingRunId?: string | null | undefined;
  selectedRunId?: string | undefined;
}

/** The instrument rail: brand, the primary "New course" action, the run-history feed, and the
 *  Settings nav — hairline-divided regions, not floating cards. Collapses to a mini icon rail: the
 *  brand + collapse toggle and the New course / Settings actions stay (as icons), the run history is
 *  hidden until expanded. The toggle stays mounted across the transition so keyboard focus persists. */
export function Sidebar({
  runs,
  onReloadRuns,
  onNewCourse,
  onOpenSettings,
  settingsActive,
  collapsed,
  onToggleCollapse,
  onSelectRun,
  onDeleteRun,
  onCancelRun,
  cancellingRunId,
  selectedRunId,
}: SidebarProps) {
  return (
    <div className={styles.sidebar} data-collapsed={collapsed || undefined}>
      <div className={styles.brand}>
        <BrandMark />
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

      <div className={styles.footer}>
        {collapsed ? (
          <button
            type="button"
            className={`${styles.railAction} ${settingsActive ? styles.railActionActive : ""}`.trim()}
            onClick={onOpenSettings}
            aria-current={settingsActive ? "page" : undefined}
            aria-label="Settings"
            title="Settings"
          >
            <GearIcon />
          </button>
        ) : (
          <button
            type="button"
            className={`${styles.navItem} ${settingsActive ? styles.navItemActive : ""}`.trim()}
            onClick={onOpenSettings}
            aria-current={settingsActive ? "page" : undefined}
          >
            Settings
          </button>
        )}
      </div>
    </div>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M8 3.25v9.5M3.25 8h9.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="2.1" stroke="currentColor" strokeWidth="1.3" />
      <path
        d="M8 1.5l.9 1.6 1.8-.4.3 1.8 1.6.9-.9 1.6.9 1.6-1.6.9-.3 1.8-1.8-.4L8 14.5l-.9-1.6-1.8.4-.3-1.8-1.6-.9.9-1.6-.9-1.6 1.6-.9.3-1.8 1.8.4z"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
    </svg>
  );
}
