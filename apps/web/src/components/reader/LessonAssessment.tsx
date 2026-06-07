import { useId, useState } from "react";

import type { AssessmentItem } from "../../types/course";
import styles from "./LessonAssessment.module.css";

/** A disclosure for a model answer: kept out of the DOM until requested (so it is never read by
 *  assistive tech while collapsed), with the trigger↔answer relationship made explicit via
 *  aria-expanded + aria-controls. */
function AnswerReveal({ answer }: { answer: string }) {
  const [open, setOpen] = useState(false);
  const answerId = useId();
  return (
    <div className={styles.answer}>
      <button
        type="button"
        className={styles.reveal}
        aria-expanded={open}
        aria-controls={answerId}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? "Hide answer" : "Show answer"}
      </button>
      {open && (
        <p id={answerId} className={styles.answerText}>
          {answer}
        </p>
      )}
    </div>
  );
}

interface LessonAssessmentProps {
  items: AssessmentItem[];
}

/** A module's assessment, shown at the end of its final lesson — each item's prompt with the
 *  gradeable bar a passing response must clear (CQ Phase 4.1) and its model answer revealable on
 *  demand. The pass criterion is absent on pre-P4 courses, so its line is shown only when present. */
export function LessonAssessment({ items }: LessonAssessmentProps) {
  return (
    <section className={styles.panel} aria-label="Check your understanding">
      <h3 className={styles.title}>Check your understanding</h3>
      <ol className={styles.list}>
        {items.map((item) => (
          <li key={item.id} className={styles.item}>
            <p className={styles.prompt}>{item.prompt}</p>
            {item.passCriterion && (
              <p className={styles.criterion}>
                <span className={styles.criterionLabel}>Passes when</span> {item.passCriterion}
              </p>
            )}
            {item.answer && <AnswerReveal answer={item.answer} />}
          </li>
        ))}
      </ol>
    </section>
  );
}
