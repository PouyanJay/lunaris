import type { NextReview } from "../../lib/reviewSchedule";
import styles from "./SessionEnded.module.css";

/** How a session ends, wherever it ends: under the transcript when the transcript is the surface,
 *  in the composer's place when the generative panel is. One component so the two surfaces cannot
 *  say it differently, and a status region so a screen reader hears the ending the moment it
 *  arrives rather than finding a locked box.
 *
 *  Real since P2c T7: when the close scheduled a review, the ending says the day and what is due
 *  on it, so a learner leaves knowing when to come back rather than reading a date off a table.
 *  `className` places it; the words and the role are fixed. */
export function SessionEnded({
  nextReview = null,
  className,
}: {
  nextReview?: NextReview | null;
  className?: string | undefined;
}) {
  return (
    <p
      className={[styles.ended, className].filter(Boolean).join(" ")}
      role="status"
      aria-label="Session ended"
    >
      This session has ended. Its record stays here, and what you demonstrated is remembered the
      next time you open this map.
      {nextReview ? (
        <>
          {" "}
          <span className={styles.comeBack}>
            Come back on {nextReview.day} for {NAMES.format(nextReview.concepts)}.
          </span>
        </>
      ) : null}
    </p>
  );
}

/** "A", "A and B", "A, B and C": the recap's own list shape (`recap_sentence._joined`), from the
 *  platform rather than by hand. British English, like the review day beside it. */
const NAMES = new Intl.ListFormat("en-GB", { style: "long", type: "conjunction" });
