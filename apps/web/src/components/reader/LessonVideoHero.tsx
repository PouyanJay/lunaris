import { useLessonVideo } from "../../hooks/useLessonVideo";
import { FAILED_REGEN_MODES, readyRegenModes, type VideoJobStatus } from "../../lib/videoJobs";
import type { VideoArtifact } from "../../types/course";
import { Button } from "../primitives/Button";
import { LunarSpinner } from "../transcript/LunarSpinner";
import { GeneratedVideoPlayer } from "./GeneratedVideoPlayer";
import { OutdatedBadge } from "./OutdatedBadge";
import { RegenerateMenu } from "./RegenerateMenu";
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

/** What each in-flight pipeline stage says under the shimmer (the worker's status machine).
 *  `ready`/`failed` exist only to keep the Record exhaustive (a new status is a compile error);
 *  the working stage never paints at a terminal status. */
const WORKING_LABELS: Record<VideoJobStatus, string> = {
  queued: "Queued",
  planning: "Planning scenes",
  coding: "Writing scenes",
  rendering: "Rendering",
  qa: "Checking quality",
  voicing: "Adding narration",
  assembling: "Assembling",
  ready: "Ready",
  failed: "Failed",
};

/** The lesson's video hero slot — the headline artifact above the prose (plan §0: hero slot).
 *
 *  One component, every state: a quiet generate affordance (idle), a shimmering 16:9 stage with a
 *  live status while the job works, the VideoFacade interaction once ready (poster → click →
 *  native player on the signed URL), a failed state with retry, the keyless refusal verbatim, and
 *  *nothing at all* when the operator kill-switch is off (a disabled feature leaves no husk). */
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

      {state.phase === "working" && <WorkingStage status={state.status} />}

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
          <span className={styles.failedTitle}>Couldn’t generate the video.</span>
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

function WorkingStage({ status }: { status: VideoJobStatus }) {
  return (
    <div className={styles.stage} role="status" aria-label="Generating lesson video">
      <span className={styles.shimmer} aria-hidden="true" />
      <span className={`mono ${styles.stageLabel}`}>
        <LunarSpinner className={styles.spinner} />
        {WORKING_LABELS[status] ?? "Working"}…
      </span>
    </div>
  );
}
