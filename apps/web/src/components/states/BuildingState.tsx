import { Button } from "../primitives/Button";
import styles from "./DataStates.module.css";

interface BuildingStateProps {
  onRecheck: () => void;
}

/** Shown when a still-running build is opened from the sidebar history. Its course isn't persisted
 *  until the run finishes, so there's nothing to render yet — an honest "in progress" state with a
 *  way to re-check, rather than a 404 error that looks broken. */
export function BuildingState({ onRecheck }: BuildingStateProps) {
  return (
    <div className={styles.center}>
      <div className={styles.message} role="status">
        <span className="eyebrow">Run in progress</span>
        <h2 className={styles.title}>Still building this course</h2>
        <p className={styles.body}>
          The agent is still working on this run. Its lessons appear here once the build finishes —
          check again in a moment, or start a new course from the sidebar.
        </p>
        <div className={styles.action}>
          <Button variant="primary" onClick={onRecheck}>
            Check again
          </Button>
        </div>
      </div>
    </div>
  );
}
