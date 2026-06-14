import { videoProgress, type VideoJobStatus } from "../../lib/videoJobs";
import styles from "./VideoProgress.module.css";

interface VideoProgressProps {
  /** The working job's current stage — drives both the bar's fill and the caption. */
  status: VideoJobStatus;
  /** Accessible context for the bar, e.g. "Generating the course trailer". */
  label: string;
}

/** The render-in-progress state for a generated video: a determinate progress bar + a plain-language
 *  stage caption, shown inside the same 16:9 stage frame as the player and the failed message (so
 *  resolving never shifts the layout). Replaces the featureless shimmer so a (re)generate reads as
 *  "working, here's how far" instead of "nothing happening". The percent + caption come from the job
 *  status the worker advances through; ``role="progressbar"`` exposes the value to assistive tech. */
export function VideoProgress({ status, label }: VideoProgressProps) {
  // `label` is the accessible context for the bar; `stageCaption` is the plain-language stage text
  // shown to everyone. Distinct concerns — kept distinctly named.
  const { percent, label: stageCaption } = videoProgress(status);
  return (
    <div className={styles.progress}>
      <p className={styles.stage}>
        <span className={styles.spinner} aria-hidden="true" />
        <span>{stageCaption}…</span>
      </p>
      <div
        className={styles.track}
        role="progressbar"
        aria-label={label}
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={`${stageCaption}, ${percent}%`}
      >
        <div className={styles.fill} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
