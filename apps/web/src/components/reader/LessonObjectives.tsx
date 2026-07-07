import type { Objective } from "../../types/course";
import styles from "./LessonObjectives.module.css";

interface LessonObjectivesProps {
  objectives: Objective[];
  /** Positions (in this module's objectives array) the learner marked understood. Absent while
   *  progress is loading/unavailable — the counter and toggles simply don't render. */
  understoodIndexes?: ReadonlySet<number> | undefined;
  /** Mark/un-mark an objective (next understood state). Absent => read-only (offline). */
  onToggleObjective?: ((objectiveIndex: number, understood: boolean) => void) | undefined;
}

/** A module's learning objectives, shown at the top of its opening lesson. Each objective carries
 *  its Bloom level as a small tag; with progress data, the header counts understanding and each
 *  objective offers a "Mark understood" toggle. */
export function LessonObjectives({
  objectives,
  understoodIndexes,
  onToggleObjective,
}: LessonObjectivesProps) {
  return (
    <section className={styles.panel} aria-label="Learning objectives">
      <div className={styles.head}>
        <h3 className={styles.title}>Learning objectives</h3>
        {understoodIndexes && (
          <span className={`${styles.counter} mono`}>
            {understoodIndexes.size} of {objectives.length} understood
          </span>
        )}
      </div>
      <ul className={styles.list}>
        {objectives.map((objective, index) => {
          const isUnderstood = understoodIndexes?.has(index) ?? false;
          return (
            <li key={`${objective.kc}-${index}`} className={styles.item}>
              <span className={styles.statement}>{objective.statement}</span>
              <span className={`${styles.bloom} mono`}>{objective.bloomLevel}</span>
              {understoodIndexes && onToggleObjective && (
                <button
                  type="button"
                  className={`${styles.toggle} mono`}
                  aria-pressed={isUnderstood}
                  data-understood={isUnderstood || undefined}
                  onClick={() => onToggleObjective(index, !isUnderstood)}
                >
                  {isUnderstood ? "✓ Understood" : "Mark understood"}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
