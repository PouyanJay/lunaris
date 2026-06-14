import { useLessonVideo } from "../../hooks/useLessonVideo";
import { FAILED_REGEN_MODES, readyRegenModes } from "../../lib/videoJobs";
import type { VideoArtifact } from "../../types/course";
import { Button } from "../primitives/Button";
import { GeneratedVideoPlayer } from "./GeneratedVideoPlayer";
import { OutdatedBadge } from "./OutdatedBadge";
import { RegenerateMenu } from "./RegenerateMenu";
import { VideoProgress } from "./VideoProgress";
import styles from "./LessonVideoHero.module.css";

interface LessonVideoHeroProps {
  apiBaseUrl: string;
  courseId: string;
  lessonId: string;
  /** The build-time lesson video, if the course shipped one. Resolved + shown with an outdated
   *  badge once the lesson is revised; absent ⇒ the on-demand generate affordance. */
  video?: VideoArtifact | null;
  /** Poll cadence override for tests; defaults to the hook's production interval. */
  pollIntervalMs?: number;
}

/** The lesson's video hero slot — the headline artifact above the prose (plan §0: hero slot).
 *
 *  One component, every state: a quiet generate affordance (idle), a 16:9 stage with a determinate
 *  progress bar + stage caption while the job works, the VideoFacade interaction once ready (poster
 *  → click → native player on the signed URL), a failed state with retry, the keyless refusal
 *  verbatim, and *nothing at all* when the operator kill-switch is off (no husk). */
export function LessonVideoHero({
  apiBaseUrl,
  courseId,
  lessonId,
  video,
  pollIntervalMs,
}: LessonVideoHeroProps) {
  const { state, generate, regenerate } = useLessonVideo(
    apiBaseUrl,
    courseId,
    lessonId,
    pollIntervalMs,
    video,
  );

  if (state.phase === "unavailable") return null;

  return (
    <section className={styles.slot} aria-label="Lesson video">
      {state.phase === "idle" && (
        <div className={styles.idle}>
          <span className={styles.idleHint}>Turn this lesson into a short animated explainer.</span>
          <Button variant="accent" onClick={generate}>
            Generate video
          </Button>
        </div>
      )}

      {state.phase === "working" && (
        <div className={styles.stage}>
          <VideoProgress status={state.status} label="Generating the lesson video" />
        </div>
      )}

      {state.phase === "ready" && (
        <>
          {/* The job just settled: announce success politely (the working status region unmounted). */}
          <span className="sr-only" role="status">
            Video ready
          </span>
          <GeneratedVideoPlayer
            videoUrl={state.videoUrl}
            posterUrl={state.posterUrl}
            captionsUrl={state.captionsUrl}
            label="Play lesson video"
          />
          <div className={styles.regenerateRow}>
            {state.stale && <OutdatedBadge />}
            <RegenerateMenu available={readyRegenModes(state.captionsUrl)} onSelect={regenerate} />
          </div>
        </>
      )}

      {state.phase === "failed" && (
        <div className={styles.failed} role="alert">
          <span className={styles.failedTitle}>
            {state.error ?? "Couldn’t generate the video."}
          </span>
          {state.jobId ? (
            <RegenerateMenu
              available={FAILED_REGEN_MODES}
              onSelect={regenerate}
              triggerLabel="Try again"
            />
          ) : (
            <Button variant="secondary" onClick={generate}>
              Try again
            </Button>
          )}
        </div>
      )}

      {state.phase === "keyless" && (
        <p className={styles.keyless} role="status">
          {state.detail}
        </p>
      )}
    </section>
  );
}
