import { CourseCover } from "./CourseCover";
import styles from "./TypographicCover.module.css";
import { coverWord } from "../../lib/coverWord";

interface TypographicCoverProps {
  /** The course topic — its most salient word is set as the ghosted display word. */
  topic: string;
  /** Stable per-course seed (a hash of the course id) — same seed, same constellation accents. */
  seed: number;
}

/** The Typographic cover: a course's resting fallback when there is no AI cover image — a keyless
 *  account (which never generates one), a cover that failed, or a course built before covers. A
 *  single ghosted topic word sits over faint seeded constellation accents on the fixed night-sky
 *  canvas (idea #3). Like `CourseCover` / `BrandMark` this is brand art with intentionally literal
 *  hues (see the CSS), so it renders identically on both themes. Decorative: the adjacent course
 *  title carries the name, so the whole thing is `aria-hidden`. */
export function TypographicCover({ topic, seed }: TypographicCoverProps) {
  return (
    <div className={styles.root} aria-hidden="true">
      <div className={styles.accents}>
        <CourseCover seed={seed} nodes={7} />
      </div>
      <span className={styles.word}>{coverWord(topic)}</span>
    </div>
  );
}
