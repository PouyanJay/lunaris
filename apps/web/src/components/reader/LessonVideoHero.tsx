import type { LessonVideoState } from "../../hooks/useLessonVideo";
import { formatMediaDuration } from "../../lib/mediaDuration";
import { FAILED_REGEN_MODES, readyRegenModes, type RegenerateMode } from "../../lib/videoJobs";
import type { VideoArtifact } from "../../types/course";
import { Button } from "../primitives/Button";
import { DegradedBadge } from "./DegradedBadge";
import { GeneratedVideoPlayer } from "./GeneratedVideoPlayer";
import { OutdatedBadge } from "./OutdatedBadge";
import { RegenerateMenu } from "./RegenerateMenu";
import { VideoProgress } from "./VideoProgress";
import styles from "./LessonVideoHero.module.css";

interface LessonVideoHeroProps {
  /** The focused lesson's video state machine. The reader owns the single `useLessonVideo`
   *  instance (so mode-independent readiness can drive the Watch mode) and passes it in. */
  state: LessonVideoState;
  generate: () => void;
  regenerate: (mode: RegenerateMode) => void;
  stop: () => void;
  refresh: () => Promise<void>;
  /** The build-time lesson video, if the course shipped one — for the honest built-duration + the
   *  scene-QA line (only trustworthy while the built artifact is what's playing). */
  video?: VideoArtifact | null | undefined;
  /** A title for the poster overlay (the owning module) — absent, the poster stays bare. */
  title?: string | undefined;
}

/** The lesson's video hero slot — the headline artifact above the prose (plan §0: hero slot).
 *
 *  One component, every state: a quiet generate affordance (idle), a 16:9 stage with a determinate
 *  progress bar + stage caption while the job works, the VideoFacade interaction once ready (poster
 *  → click → native player on the signed URL), a failed state with retry, the keyless refusal
 *  verbatim, and *nothing at all* when the operator kill-switch is off (no husk). Presentational:
 *  the reader drives the state machine and hands it in. */
export function LessonVideoHero({
  state,
  generate,
  regenerate,
  stop,
  refresh,
  video,
  title,
}: LessonVideoHeroProps) {
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
          {/* The plain player. A ready video with a chapter outline is the Watch mode's surface
              now (the reader mounts this hero only when there's no such outline — a not-yet-ready,
              or a pre-Cinema un-chaptered, video), so this is always the plain player. */}
          <GeneratedVideoPlayer
            videoUrl={state.videoUrl}
            posterUrl={state.posterUrl}
            captionsUrl={state.captionsUrl}
            label="Play lesson video"
            refreshPlayback={refresh}
            overlayTitle={title}
          />
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
