import { Button } from "../primitives/Button";
import { BrandMark } from "./BrandMark";
import { RunList } from "./RunList";
import { SidebarToggle } from "./SidebarToggle";
import { ThemeToggle } from "./ThemeToggle";
import type { RunsState } from "../../hooks/useRuns";
import type { ThemeProps } from "../../hooks/useTheme";
import type { CourseRun } from "../../types/course";
import styles from "./Sidebar.module.css";

interface SidebarProps extends ThemeProps {
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
  theme,
  onToggleTheme,
}: SidebarProps) {
  return (
    <div className={styles.sidebar} data-collapsed={collapsed || undefined}>
      <div className={styles.brand}>
        <BrandMark size={24} />
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
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>
    </div>
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
