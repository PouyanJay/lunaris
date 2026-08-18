import type { ReactNode } from "react";

import styles from "./Speech.module.css";

/** What the tutor said, printed as written: prose at reading size, whitespace kept, and never
 *  interpreted — the tutor is asked for plain words (no markdown), and a renderer that reformatted
 *  them would be a second author. Shared by the transcript (the record) and the CopilotKit panel
 *  (the live turn), so the same turn reads the same on both. `Speech.module.css` also owns the turn
 *  row both surfaces compose from, for the same reason. */
export function TutorSpeech({ children }: { children: ReactNode }) {
  return <p className={styles.tutor}>{children}</p>;
}

/** The pause between the voices — an answer with the grader, a tutor still writing — as a quiet
 *  announced line rather than a spinner: the wait is a state of the session, not a gap in it. */
export function Working({ children }: { children: string }) {
  return (
    <p className={styles.working} role="status">
      {children}
    </p>
  );
}

/** What the learner said, under its own label. The label is text, not colour, so a screen-reader
 *  user hears whose words follow. */
export function LearnerSpeech({ children }: { children: ReactNode }) {
  return (
    <>
      <p className={styles.learnerLabel}>You</p>
      <p className={styles.answer}>{children}</p>
    </>
  );
}
