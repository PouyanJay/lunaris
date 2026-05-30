import { Button } from "../primitives/Button";
import styles from "./DataStates.module.css";

interface EmptyStateProps {
  onReload: () => void;
}

/** Shown when a course loaded but its prerequisite graph has no concepts yet. */
export function EmptyState({ onReload }: EmptyStateProps) {
  return (
    <div className={styles.center}>
      <div className={styles.message}>
        <span className="eyebrow">Prerequisite graph</span>
        <h2 className={styles.title}>No concepts yet</h2>
        <p className={styles.body}>
          This course hasn&rsquo;t been mapped into knowledge components. Once the agent runs the
          concept extractor and graph builder, the learning path appears here.
        </p>
        <div className={styles.action}>
          <Button variant="primary" onClick={onReload}>
            Reload course
          </Button>
        </div>
      </div>
    </div>
  );
}
