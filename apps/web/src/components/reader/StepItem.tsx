import { useId, useState, type ReactNode } from "react";

import styles from "./Stepper.module.css";

interface StepItemProps {
  /** The step's number, lowered from the prose label ("Step 3:" → "3"). */
  number?: string;
  /** The step heading (label + title sentence). */
  heading?: string;
  children?: ReactNode;
}

/** One step in the Stepper infographic: a numbered node beside a titled, collapsible card. Two
 *  independent controls — the numbered node is a mark-as-done toggle (pressed state + check glyph, so
 *  a learner tracks progress), and the heading is a disclosure that expands/collapses the step body
 *  (open by default). Completion is never conveyed by colour alone (WCAG). */
export function StepItem({ number, heading, children }: StepItemProps) {
  const [done, setDone] = useState(false);
  const [open, setOpen] = useState(true);
  const label = number ?? "";
  const bodyId = useId();

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
        <button
          type="button"
          className={styles.headingToggle}
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((prev) => !prev)}
        >
          <span className={styles.chevron} data-open={open} aria-hidden="true">
            ▸
          </span>
          <span className={styles.heading}>{heading}</span>
        </button>
        <div id={bodyId} className={styles.body} hidden={!open}>
          {children}
        </div>
      </div>
    </li>
  );
}
