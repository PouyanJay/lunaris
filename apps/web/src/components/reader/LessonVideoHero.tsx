import { useLessonVideo } from "../../hooks/useLessonVideo";
import { formatMediaDuration } from "../../lib/mediaDuration";
import { FAILED_REGEN_MODES, readyRegenModes } from "../../lib/videoJobs";
import type { VideoArtifact } from "../../types/course";
import { Button } from "../primitives/Button";
import { DegradedBadge } from "./DegradedBadge";
import { CinemaPlayer } from "./CinemaPlayer";
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
  /** A title for the poster overlay (the owning module) — absent, the poster stays bare. */
  title?: string | undefined;
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
  title,
  pollIntervalMs,
}: LessonVideoHeroProps) {
  const { state, generate, regenerate, stop, refresh } = useLessonVideo(
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
          <VideoProgress status={state.status} label="Generating the lesson video" onStop={stop} />
        </div>
      )}

      {state.phase === "stopped" && (
        <div className={styles.stopped}>
          <span className={styles.idleHint} role="status">
            Generation stopped.
          </span>
          <Button variant="accent" onClick={generate}>
            Generate video
          </Button>
        </div>
      )}

      {state.phase === "ready" && (
        <>
          {/* The job just settled: announce success politely (the working status region unmounted). */}
          <span className="sr-only" role="status">
            Video ready
          </span>
          {/* Cinema (phase 5): a ready video with a derived outline plays as a chaptered,
              transcript-synced surface — the video-led front door. Videos with no chapters (a
              pre-Cinema render) fall back to the plain player. */}
          {state.chapters.length > 0 ? (
            <CinemaPlayer
              videoUrl={state.videoUrl}
              posterUrl={state.posterUrl}
              captionsUrl={state.captionsUrl}
              chapters={state.chapters}
              transcript={state.transcript}
              label={title ? `${title} — lesson video` : "Lesson video"}
            />
          ) : (
            <GeneratedVideoPlayer
              videoUrl={state.videoUrl}
              posterUrl={state.posterUrl}
              captionsUrl={state.captionsUrl}
              label="Play lesson video"
              refreshPlayback={refresh}
              overlayTitle={title}
            />
          )}
          <div className={styles.metaRow}>
            <span className={`mono ${styles.metaCaption}`}>
              Lesson video
              {/* The built duration is only honest while the built artifact is what's playing. */}
              {video?.durationS != null &&
                state.jobId === video.jobId &&
                !state.stale &&
                ` · ${formatMediaDuration(video.durationS)}`}
            </span>
            <div className={styles.metaEnd}>
              {/* Honesty-gated (AD-3): every scene passed visual QA and the lesson hasn't been
                  revised since — otherwise the badges tell the real story. */}
              {!state.stale && state.degradedScenes.length === 0 && (
                <span className={`mono ${styles.verified}`}>
                  <span className={styles.verifiedDot} aria-hidden="true" />
                  All scenes verified
                </span>
              )}
              {state.stale && <OutdatedBadge />}
              <DegradedBadge scenes={state.degradedScenes} />
              <RegenerateMenu
                available={readyRegenModes(state.captionsUrl)}
                onSelect={regenerate}
              />
            </div>
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
