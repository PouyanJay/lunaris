import { useCallback, useEffect, useRef, useState } from "react";

import {
  cancelVideoJob,
  fetchFreshPlaybackUrls,
  fetchVideoJob,
  findActiveVideoJobByCoordinates,
  pollVideoJob,
  regenerateVideo,
  resolveJobId,
  type RegenerateMode,
  type VideoJobStatus,
} from "../lib/videoJobs";
import type { DegradedScene, VideoArtifact } from "../types/course";

export const COURSE_VIDEO_POLL_INTERVAL_MS = 2500;

/** What the Overview section knows about one course-level video. A build-time artifact is already
 *  terminal in the payload, so the resting states are ready / failed; `working` appears only while a
 *  regenerate (V6) the user triggered is in flight. `ready` carries `stale` (the outdated badge) and
 *  `degradedScenes` (scenes shipped flagged — the degraded badge). */
export type CourseVideoState =
  | { phase: "absent" }
  | { phase: "loading" }
  | { phase: "working"; status: VideoJobStatus }
  | {
      phase: "ready";
      videoUrl: string;
      posterUrl: string | null;
      captionsUrl: string | null;
      stale: boolean;
      degradedScenes: DegradedScene[];
    }
  | { phase: "failed"; error?: string | null }
  | { phase: "stopped" };

/** Resolve a course video's playable state from its payload artifact, and let the reader regenerate
 *  it (explainer-video V5 + V6).
 *
 *  The build already rendered (or degraded) these, so a READY artifact carries `provenance.jobId`,
 *  exchanged for short-lived signed URLs via `GET /api/videos/{jobId}`. `regenerate(mode)` re-runs
 *  the artifact's job (READY *or* FAILED — both carry `jobId`) and polls the new job to a verdict,
 *  so a failed course video gets a retry path the published payload can't otherwise offer. */
export function useCourseVideo(
  apiBaseUrl: string | undefined,
  courseId: string | undefined,
  artifact: VideoArtifact | null | undefined,
  pollIntervalMs: number = COURSE_VIDEO_POLL_INTERVAL_MS,
): {
  state: CourseVideoState;
  regenerate: (mode: RegenerateMode) => void;
  stop: () => void;
  refresh: () => Promise<void>;
} {
  // Depend on scalars (status + jobId + kind), not the artifact object — Course is re-serialised on
  // every poll, so a new object reference each render would re-fire the fetch even when nothing
  // changed. `kind` keys the coordinate re-attach probe (summary vs overview).
  const status = artifact?.status ?? null;
  const kind = artifact?.kind ?? null;
  const jobId = resolveJobId(artifact);
  const readyJobId = status === "ready" ? jobId : null;
  const [state, setState] = useState<CourseVideoState>(() =>
    initialState(apiBaseUrl, status, jobId),
  );
  const controllerRef = useRef<AbortController | null>(null);
  // The job whose URLs are currently on screen (the built ready job, or a re-attached/regenerated
  // one). Used to re-mint the signed URLs on playback error — they expire ~1h after they resolve.
  const shownJobIdRef = useRef<string | null>(null);
  // The last successful video shown for this slot (state + its job). Stopping a regenerate (or
  // seeing the job cancelled elsewhere) snaps back to it rather than a "stopped" placeholder — so a
  // mid-regenerate stop returns you to what was already playing, no refresh needed.
  const lastReadyRef = useRef<{
    state: Extract<CourseVideoState, { phase: "ready" }>;
    jobId: string;
  } | null>(null);

  const stopPolling = useCallback(() => controllerRef.current?.abort(), []);

  // Settle a stopped/cancelled job: revert to the last successful video if there is one (re-pointing
  // the shown job so a refresh re-mints the restored URLs), else the stopped affordance (a slot with
  // no prior success has nothing to fall back to).
  const settleStopped = useCallback(() => {
    const lastReady = lastReadyRef.current;
    if (lastReady) {
      shownJobIdRef.current = lastReady.jobId;
      setState(lastReady.state);
    } else {
      setState({ phase: "stopped" });
    }
  }, []);

  // Watch one job to a verdict: working while it renders, ready/failed once it settles. Shared by
  // the regenerate path and the on-mount re-attach so both surface progress identically.
  const watch = useCallback(
    (watchJobId: string) => {
      if (!apiBaseUrl) return;
      shownJobIdRef.current = watchJobId;
      stopPolling();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ phase: "working", status: "queued" });
      void pollVideoJob(apiBaseUrl, watchJobId, {
        signal: controller.signal,
        intervalMs: pollIntervalMs,
        onWorking: (workingStatus) => setState({ phase: "working", status: workingStatus }),
        onSettled: (view) =>
          view.job.status === "cancelled"
            ? settleStopped()
            : setState(toCourseVideoState(view)),
      });
    },
    [apiBaseUrl, pollIntervalMs, stopPolling, settleStopped],
  );

  // Track the last successful video so a stop can restore it (kept in sync with refresh's re-mint).
  useEffect(() => {
    if (state.phase === "ready" && shownJobIdRef.current) {
      lastReadyRef.current = { state, jobId: shownJobIdRef.current };
    }
  }, [state]);

  useEffect(() => {
    stopPolling();
    lastReadyRef.current = null; // the slot changed — the prior video belonged to the old artifact
    if (status !== "ready" || !readyJobId || !apiBaseUrl) {
      setState(initialState(apiBaseUrl, status, jobId)); // absent / failed — resolve via the probe
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    shownJobIdRef.current = readyJobId;
    setState({ phase: "loading" });
    void fetchVideoJob(apiBaseUrl, readyJobId, controller.signal).then((view) => {
      if (controller.signal.aborted) return;
      setState(toCourseVideoState(view));
    });
    return () => controller.abort();
  }, [apiBaseUrl, readyJobId, jobId, status, stopPolling]);

  // Derive-at-read re-attach: resolve the slot from the live queue by its COORDINATES (course, kind)
  // on the null-lesson path, needing no source job id. This recovers a course-video slot whose
  // payload pointer is FAILED-with-a-job-that-has-since-gone-READY — the async-after-delivery case
  // the source-job probe missed (when the build job ITSELF flips FAILED→READY it answers 204). It
  // also catches an in-flight or completed regenerate. A live job wins over the stale built state, so
  // a render survives a refresh / navigate-away instead of the slot showing the old failed state.
  useEffect(() => {
    if (!apiBaseUrl || !courseId || !kind) return;
    const controller = new AbortController();
    void findActiveVideoJobByCoordinates(
      apiBaseUrl,
      courseId,
      kind,
      undefined,
      controller.signal,
    ).then((view) => {
      if (controller.signal.aborted) return;
      if (view && view.job.id !== readyJobId) {
        // A live or newer take the built artifact can't see. Skip when it's the READY job the
        // effect above already fetched (don't double-poll a slot).
        watch(view.job.id);
      } else if (!view && status === "failed") {
        // No live job and no successful take: settle on the honest failed state (the loading state
        // above only deferred it until this probe resolved).
        setState({ phase: "failed" });
      }
    });
    return () => controller.abort();
  }, [apiBaseUrl, courseId, kind, readyJobId, status, watch]);

  const regenerate = useCallback(
    (mode: RegenerateMode) => {
      if (!apiBaseUrl || !jobId) return;
      stopPolling();
      setState({ phase: "working", status: "queued" });
      void regenerateVideo(apiBaseUrl, jobId, mode).then((result) => {
        if (result.kind !== "accepted") {
          setState({ phase: "failed" });
          return;
        }
        watch(result.view.job.id);
      });
    },
    [apiBaseUrl, jobId, watch, stopPolling],
  );

  // Stop the in-flight job (a regenerate, or a build-time render the slot re-attached to): drop to
  // the stopped state at once and tell the server to cancel it, so the worker spends no further
  // compute. Aborting the poll first keeps it from racing the stopped state back to working.
  const stop = useCallback(() => {
    const id = shownJobIdRef.current;
    if (!apiBaseUrl || !id) return;
    stopPolling();
    void cancelVideoJob(apiBaseUrl, id);
    settleStopped(); // revert to the last good video if there is one, else show stopped
  }, [apiBaseUrl, stopPolling, settleStopped]);

  // Re-mint the shown job's short-lived signed URLs (they expire ~1h after they resolve). The player
  // calls this when its <video> fails to load the expired URL; we re-fetch the same job and swap
  // fresh URLs into the ready state, remounting the player on the live URL — no page reload.
  const refresh = useCallback(async () => {
    const id = shownJobIdRef.current;
    if (!apiBaseUrl || !id) return;
    const fresh = await fetchFreshPlaybackUrls(apiBaseUrl, id);
    if (!fresh || shownJobIdRef.current !== id) return; // gone, not ready, or the slot moved on
    setState((prev) =>
      prev.phase === "ready"
        ? {
            ...prev,
            videoUrl: fresh.videoUrl,
            posterUrl: fresh.posterUrl,
            captionsUrl: fresh.captionsUrl,
            stale: fresh.stale ?? prev.stale,
          }
        : prev,
    );
  }, [apiBaseUrl]);

  return { state, regenerate, stop, refresh };
}

function toCourseVideoState(
  view: {
    job?: { error?: string | null };
    videoUrl: string | null;
    posterUrl: string | null;
    captionsUrl: string | null;
    provenance?: { degradedScenes?: DegradedScene[] } | null;
    stale?: boolean;
  } | null,
): CourseVideoState {
  return view?.videoUrl
    ? {
        phase: "ready",
        videoUrl: view.videoUrl,
        posterUrl: view.posterUrl,
        captionsUrl: view.captionsUrl,
        stale: view.stale ?? false,
        degradedScenes: view.provenance?.degradedScenes ?? [],
      }
    : { phase: "failed", error: view?.job?.error ?? null };
}

function initialState(
  apiBaseUrl: string | undefined,
  status: VideoArtifact["status"] | null,
  jobId: string | null,
): CourseVideoState {
  if (status === null) return { phase: "absent" };
  // No api base or no resolvable jobId → the honest failed state. Otherwise start loading: a READY
  // artifact until its signed URL comes back (no broken-player flash), and a FAILED one until the
  // re-attach probe settles — it may surface a successful regenerate the payload doesn't point to,
  // so we resolve before showing the failed message rather than flashing it.
  if (!jobId || !apiBaseUrl) return { phase: "failed" };
  return { phase: "loading" };
}
