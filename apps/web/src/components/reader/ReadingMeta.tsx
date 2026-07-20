import type { CSSProperties } from "react";

import styles from "./ReadingMeta.module.css";

interface ReadingMetaProps {
  /** Estimated minutes to read the focused lesson (≥ 1). */
  minutes: number;
  /** How much of the lesson has been scrolled past, 0–100. */
  percent: number;
}

/** The Field Guide reading-meta band: estimated reading time, a hairline progress track, and the
 *  live percent read — the at-a-glance answer to "how big is this lesson and where am I in it". */
export function ReadingMeta({ minutes, percent }: ReadingMetaProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div
      className={styles.band}
      role="group"
      aria-label="Reading progress"
      style={{ "--reading-percent": `${clamped}%` } as CSSProperties}
    >
      <span className={styles.metric}>{minutes} min read</span>
      <span className={styles.track} aria-hidden="true">
        <span className={styles.fill} />
      </span>
      <span className={styles.percent}>{clamped}% read</span>
    </div>
  );
}
