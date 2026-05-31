import type { StepsSpec } from "../../../types/course";
import styles from "./visuals.module.css";

interface StepsDiagramProps {
  spec: StepsSpec;
}

/** A branded ordered-process diagram: numbered steps with optional detail. */
export function StepsDiagram({ spec }: StepsDiagramProps) {
  return (
    <ol className={styles.steps}>
      {spec.steps.map((step, index) => (
        <li key={index} className={styles.step}>
          <span className={`${styles.stepIndex} mono`} aria-hidden="true">
            {index + 1}
          </span>
          <div className={styles.stepBody}>
            <p className={styles.stepTitle}>{step.title}</p>
            {step.detail && <p className={styles.stepDetail}>{step.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
