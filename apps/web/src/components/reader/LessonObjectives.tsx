import type { Objective } from "../../types/course";
import styles from "./LessonObjectives.module.css";

interface LessonObjectivesProps {
  objectives: Objective[];
}

/** A module's learning objectives, shown at the top of its opening lesson. Each objective carries
 *  its Bloom level as a small tag. */
export function LessonObjectives({ objectives }: LessonObjectivesProps) {
  return (
    <section className={styles.panel} aria-label="Learning objectives">
      <h3 className={styles.title}>Learning objectives</h3>
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
