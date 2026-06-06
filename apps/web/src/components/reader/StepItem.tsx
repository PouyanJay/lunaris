import { useState, type ReactNode } from "react";

import styles from "./Stepper.module.css";

interface StepItemProps {
  /** The step's number, lowered from the prose label ("Step 3:" → "3"). */
  number?: string;
  /** The step heading (label + title sentence). */
  heading?: string;
  children?: ReactNode;
}

/** One step in the Stepper infographic: a numbered node beside a titled card. The node is a real
 *  toggle button — pressing it marks the step done (the number becomes a check and the card dims), so
 *  the learner can track progress. The completion state is conveyed by the button's pressed state and
 *  a glyph, never by colour alone (WCAG). */
export function StepItem({ number, heading, children }: StepItemProps) {
  const [done, setDone] = useState(false);
  const label = number ?? "";

  return (
    <li className={`${styles.step} ${done ? styles.stepDone : ""}`}>
      <button
        type="button"
        className={styles.node}
        aria-pressed={done}
        aria-label={done ? `Step ${label} done` : `Mark step ${label} done`}
        onClick={() => setDone((prev) => !prev)}
      >
        <span className={`mono ${styles.nodeLabel}`} aria-hidden="true">
          {done ? "✓" : label}
        </span>
      </button>
      <div className={styles.card}>
        {heading && <p className={styles.heading}>{heading}</p>}
        <div className={styles.body}>{children}</div>
      </div>
    </li>
  );
}
