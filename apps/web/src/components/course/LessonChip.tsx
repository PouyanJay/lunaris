import type { LessonState } from "../../lib/lessonState";
import styles from "./LessonChip.module.css";

interface LessonChipProps {
  /** The lesson's 1-based number in course order — the chip's face until the lesson is done. */
  number: number;
  state: LessonState;
  /** `md` for Overview rows (36px), `sm` for the reader's outline rail (24px). */
  size?: "md" | "sm";
}

/** The numbered lesson chip shared by the Overview's rows and the reader's outline: a mono
 *  numeral that flips to the done glyph, tinted by progress state. Decorative (aria-hidden) —
 *  the owning row or entry carries the accessible state in its text. */
export function LessonChip({ number, state, size = "md" }: LessonChipProps) {
  return (
    <span
      className={`${styles.chip} ${size === "sm" ? styles.sm : ""}`.trim()}
      data-state={state}
      aria-hidden="true"
    >
      {state === "done" ? "✓" : number}
    </span>
  );
}
