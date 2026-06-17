import { Button } from "../primitives/Button";
import { videoProgress, type VideoJobStatus } from "../../lib/videoJobs";
import styles from "./VideoProgress.module.css";

interface VideoProgressProps {
  /** The working job's current stage — drives both the bar's fill and the caption. */
  status: VideoJobStatus;
  /** Accessible context for the bar, e.g. "Generating the course trailer". */
  label: string;
  /** When set, a Stop control is shown that cancels the in-flight job (no further compute is spent).
   *  Omitted ⇒ no stop affordance (e.g. progress shown where cancelling does not apply). */
  onStop?: () => void;
}

/** The render-in-progress state for a generated video: a determinate progress bar + a plain-language
 *  stage caption, shown inside the same 16:9 stage frame as the player and the failed message (so
 *  resolving never shifts the layout). Replaces the featureless shimmer so a (re)generate reads as
 *  "working, here's how far" instead of "nothing happening". The percent + caption come from the job
 *  status the worker advances through; ``role="progressbar"`` exposes the value to assistive tech.
 *  When ``onStop`` is given, a Stop button lets the user cancel the render mid-flight. */
export function VideoProgress({ status, label, onStop }: VideoProgressProps) {
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
      {onStop && (
        <div className={styles.actions}>
          <Button variant="secondary" onClick={onStop} aria-label={`Stop — ${label}`}>
            Stop
          </Button>
        </div>
      )}
    </div>
  );
}
