import styles from "./SessionEnded.module.css";

/** The one sentence a session ends on, wherever it ends: under the transcript when the transcript
 *  is the surface, in the composer's place when the generative panel is. One component so the two
 *  surfaces cannot say it differently, and a status region so a screen reader hears the ending
 *  the moment it arrives rather than finding a locked box.
 *
 *  `className` places it; the words and the role are fixed. */
export function SessionEnded({ className }: { className?: string | undefined }) {
  return (
    <p
      className={[styles.ended, className].filter(Boolean).join(" ")}
      role="status"
      aria-label="Session ended"
    >
      This session has ended. Its record stays here, and what you demonstrated is remembered the
      next time you open this map.
    </p>
  );
}
