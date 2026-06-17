import type { BuildVideoProgress } from "../../hooks/useBuildVideoProgress";
import { Button } from "../primitives/Button";
import styles from "./VideosGeneratingPanel.module.css";

interface VideosGeneratingPanelProps {
  /** The live N-of-M reading, or null before the first poll lands (the loading affordance). */
  progress: BuildVideoProgress | null;
  /** Leave the build canvas for the course now, without waiting for the videos to finish. */
  onOpenCourse: () => void;
}

/** The build canvas's videos phase: after the build run completes, the lesson + course videos keep
 *  rendering async on the cloud worker (minutes, after the build SSE has ended), so this panel polls
 *  their status and shows a determinate "N of M ready" bar in their place — the canvas no longer
 *  appears frozen on the last build phase. The course is already readable, so "Open course" is the
 *  primary action (the user is never forced to wait); the canvas advances on its own once every video
 *  settles. Honest about failures: a video that couldn't generate is named, with a retry pointer. */
export function VideosGeneratingPanel({ progress, onOpenCourse }: VideosGeneratingPanelProps) {
  const progressPercent =
    progress && progress.total > 0 ? (progress.ready / progress.total) * 100 : 0;
  return (
    <section className={styles.panel} aria-label="Video generation progress">
      <div className={styles.head}>
        <div className={styles.heading}>
          <p className="eyebrow">Almost there</p>
          <h3 className={styles.title}>Generating videos…</h3>
        </div>
        <Button variant="primary" onClick={onOpenCourse}>
          Open course
        </Button>
      </div>

      {progress === null ? (
        <p className={styles.caption} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          Finishing up your videos…
        </p>
      ) : (
        <>
          <div className={styles.meter}>
            <div
              className={styles.track}
              role="progressbar"
              aria-label="Generating videos"
              aria-valuenow={progress.ready}
              aria-valuemin={0}
              aria-valuemax={progress.total}
              aria-valuetext={`${progress.ready} of ${progress.total} videos ready`}
            >
              <div className={styles.fill} style={{ width: `${progressPercent}%` }} />
            </div>
            <span className={`mono ${styles.count}`} aria-live="polite">
              {progress.ready} / {progress.total}
            </span>
          </div>
          <p className={styles.caption}>
            Your course is ready to read — videos keep rendering in the background and appear as
            they finish.
            {progress.failed > 0 && (
              <span className={styles.failed}>
                {" "}
                {progress.failed} couldn’t generate — retry {progress.failed === 1 ? "it" : "them"}{" "}
                from the lesson.
              </span>
            )}
          </p>
        </>
      )}
    </section>
  );
}
