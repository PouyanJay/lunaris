import { Button } from "../primitives/Button";
import { RunList } from "./RunList";
import type { RunsState } from "../../hooks/useRuns";
import type { CourseRun } from "../../types/course";
import styles from "./Sidebar.module.css";

interface SidebarProps {
  runs: RunsState;
  onReloadRuns: () => void;
  onNewCourse: () => void;
  onOpenSettings: () => void;
  settingsActive: boolean;
  onSelectRun?: ((run: CourseRun) => void) | undefined;
  selectedRunId?: string | undefined;
}

/** The instrument rail: brand, the primary "New course" action, the run-history feed, and the
 *  Settings nav — hairline-divided regions, not floating cards. */
export function Sidebar({
  runs,
  onReloadRuns,
  onNewCourse,
  onOpenSettings,
  settingsActive,
  onSelectRun,
  selectedRunId,
}: SidebarProps) {
  return (
    <div className={styles.sidebar}>
      <div className={styles.brand}>
        <span className={styles.mark} aria-hidden="true" />
        <span className={styles.wordmark}>Lunaris</span>
      </div>

      <div className={styles.actions}>
        <Button variant="primary" className={styles.newCourse} onClick={onNewCourse}>
          New course
        </Button>
      </div>

      <nav className={styles.history} aria-label="Run history">
        <span className={`eyebrow ${styles.sectionLabel}`}>Recent runs</span>
        <RunList
          state={runs}
          onRetry={onReloadRuns}
          onSelectRun={onSelectRun}
          selectedRunId={selectedRunId}
        />
      </nav>

      <div className={styles.footer}>
        <button
          type="button"
          className={`${styles.navItem} ${settingsActive ? styles.navItemActive : ""}`.trim()}
          onClick={onOpenSettings}
          aria-current={settingsActive ? "page" : undefined}
        >
          Settings
        </button>
      </div>
    </div>
  );
}
