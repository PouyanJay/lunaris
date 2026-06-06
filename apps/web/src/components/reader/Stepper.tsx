import type { ReactNode } from "react";

import styles from "./Stepper.module.css";

/** An interactive step infographic for multi-step instructions (lifted from a "Step 1: … Step 2: …"
 *  prose run). It renders as a real ordered list with a numbered spine connecting the steps; each
 *  StepItem child carries its own number, heading, and body. The numbered nodes double as
 *  mark-as-done toggles so a learner can track progress through the procedure. */
export function Stepper({ children }: { children?: ReactNode }) {
  return (
    <ol className={styles.stepper} aria-label="Steps">
      {children}
    </ol>
  );
}
