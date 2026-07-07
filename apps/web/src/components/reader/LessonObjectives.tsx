import type { Objective } from "../../types/course";
import styles from "./LessonObjectives.module.css";

interface LessonObjectivesProps {
  objectives: Objective[];
  /** Positions (in this module's objectives array) the learner marked understood. Absent while
   *  progress is loading/unavailable — the counter simply doesn't render. */
  understoodIndexes?: ReadonlySet<number> | undefined;
}

/** A module's learning objectives, shown at the top of its opening lesson. Each objective carries
 *  its Bloom level as a small tag; with progress data, the header counts understanding. */
export function LessonObjectives({ objectives, understoodIndexes }: LessonObjectivesProps) {
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
        {objectives.map((objective, index) => (
          <li key={`${objective.kc}-${index}`} className={styles.item}>
            <span className={styles.statement}>{objective.statement}</span>
            <span className={`${styles.bloom} mono`}>{objective.bloomLevel}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
