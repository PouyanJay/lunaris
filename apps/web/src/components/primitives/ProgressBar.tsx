import styles from "./ProgressBar.module.css";

interface ProgressBarProps {
  /** 0..1 — a determinate bar; callers with no real measure shouldn't use a progress bar. */
  value: number;
  /** Announced name for the bar (what is progressing), e.g. "Model download". */
  label: string;
  /** Fill hue: accent for live work (default), success for a finished measure. Never the sole
   *  signal — callers pair the bar with a textual status. */
  tone?: "accent" | "success";
}

/** The determinate progress bar primitive: a hairline track with a toned fill, announced via
 *  the progressbar role. Shared by every surface that reports a real 0..1 measure (the on-device
 *  model download in explains and device builds, the library cards' course progress). */
export function ProgressBar({ value, label, tone = "accent" }: ProgressBarProps) {
  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div
      className={styles.track}
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div className={styles.fill} data-tone={tone} style={{ width: `${percent}%` }} />
    </div>
  );
}
