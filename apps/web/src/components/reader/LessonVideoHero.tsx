import { useEffect, useRef, useState } from "react";

import { useLessonVideo } from "../../hooks/useLessonVideo";
import type { VideoJobStatus } from "../../lib/videoJobs";
import { Button } from "../primitives/Button";
import { LunarSpinner } from "../transcript/LunarSpinner";
import styles from "./LessonVideoHero.module.css";

interface LessonVideoHeroProps {
  apiBaseUrl: string;
  courseId: string;
  lessonId: string;
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
  pollIntervalMs,
}: LessonVideoHeroProps) {
  const { state, generate } = useLessonVideo(apiBaseUrl, courseId, lessonId, pollIntervalMs);

  if (state.phase === "unavailable") return null;

  return (
    <section className={styles.slot} aria-label="Lesson video">
      {state.phase === "idle" && (
        <div className={styles.idle}>
          <span className={styles.idleHint}>
            Turn this lesson into a short animated explainer.
          </span>
          <Button variant="accent" onClick={generate}>
            Generate video
          </Button>
        </div>
      )}

      {state.phase === "working" && <WorkingStage status={state.status} />}

      {state.phase === "ready" && (
        <ReadyPlayer videoUrl={state.videoUrl} posterUrl={state.posterUrl} />
      )}

      {state.phase === "failed" && (
        <div className={styles.failed} role="alert">
          <span className={styles.failedTitle}>Couldn’t generate the video.</span>
          <Button variant="secondary" onClick={generate}>
            Try again
          </Button>
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

function ReadyPlayer({ videoUrl, posterUrl }: { videoUrl: string; posterUrl: string | null }) {
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Playing unmounts the focused poster button — move focus onto the player so keyboard users
  // land on the controls instead of falling back to <body> (WCAG 2.4.3).
  useEffect(() => {
    if (playing) videoRef.current?.focus();
  }, [playing]);

  return (
    <div className={styles.stage}>
      {/* The job just settled: announce success politely (the working status region unmounted). */}
      <span className="sr-only" role="status">
        Video ready
      </span>
      {playing ? (
        /* The artifact is our own MP4 on a signed URL — a native element, no third party.
           Captions arrive with narrated videos in V3 (the silent stub has none to caption). */
        <video
          ref={videoRef}
          className={styles.player}
          src={videoUrl}
          poster={posterUrl ?? undefined}
          controls
          autoPlay
        />
      ) : (
        <button
          type="button"
          className={styles.poster}
          aria-label="Play lesson video"
          onClick={() => setPlaying(true)}
        >
          {posterUrl ? (
            <img className={styles.posterImage} src={posterUrl} alt="" loading="lazy" />
          ) : (
            <span className={`mono ${styles.posterGlyph}`} aria-hidden="true">
              VIDEO
            </span>
          )}
          <span className={styles.play} aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
        </button>
      )}
    </div>
  );
}
