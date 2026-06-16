import { useCallback, useEffect, useRef, useState } from "react";

import {
  enqueueLessonVideo,
  fetchFreshPlaybackUrls,
  findActiveVideoJob,
  pollVideoJob,
  regenerateVideo,
  resolveJobId,
  type RegenerateMode,
  type VideoJobStatus,
} from "../lib/videoJobs";
import type { VideoArtifact } from "../types/course";

export const VIDEO_POLL_INTERVAL_MS = 2500;

/** The hero slot's whole state machine, one discriminated union. `ready`/`failed` carry the source
 *  `jobId` so the regenerate menu (V6) can re-run them; `ready` also carries `stale` (the lesson was
 *  revised since — the outdated badge, V6-T3). `failed` is `null` only when the enqueue itself never
 *  produced a job. */
export type LessonVideoState =
  | { phase: "idle" }
  | { phase: "working"; status: VideoJobStatus }
  | {
      phase: "ready";
      jobId: string;
      videoUrl: string;
      posterUrl: string | null;
      captionsUrl: string | null;
      stale: boolean;
    }
  | { phase: "failed"; jobId: string | null; error?: string | null }
  | { phase: "keyless"; detail: string }
  | { phase: "unavailable" };

/** Drives one lesson's video: it resolves the build-time `video` (if the course shipped one — the
 *  hero shows it with an outdated badge once the lesson is revised), `generate()` enqueues an
 *  on-demand one, and `regenerate(mode)` re-runs the current job through the menu (V6). State resets
 *  when the lesson changes — the slot always describes the lesson on screen. An on-demand binding
 *  lives in memory only: reloading falls back to the build-time video, or idle when there is none. */
export function useLessonVideo(
  apiBaseUrl: string,
  courseId: string,
  lessonId: string,
  pollIntervalMs: number = VIDEO_POLL_INTERVAL_MS,
  video?: VideoArtifact | null,
): {
  state: LessonVideoState;
  generate: () => void;
  regenerate: (mode: RegenerateMode) => void;
  refresh: () => Promise<void>;
} {
  const [state, setState] = useState<LessonVideoState>({ phase: "idle" });
  const controllerRef = useRef<AbortController | null>(null);
  const jobIdRef = useRef<string | null>(null);

  const stopPolling = useCallback(() => controllerRef.current?.abort(), []);

  const watch = useCallback(
    (jobId: string) => {
      jobIdRef.current = jobId;
      stopPolling();
      const controller = new AbortController();
      controllerRef.current = controller;
      void pollVideoJob(apiBaseUrl, jobId, {
        signal: controller.signal,
        intervalMs: pollIntervalMs,
        onWorking: (status) => setState({ phase: "working", status }),
        onSettled: (view) => {
          if (view.job.status === "ready" && view.videoUrl) {
            setState({
              phase: "ready",
              jobId,
              videoUrl: view.videoUrl,
              posterUrl: view.posterUrl,
              captionsUrl: view.captionsUrl,
              stale: view.stale ?? false,
            });
          } else {
            setState({ phase: "failed", jobId, error: view.job.error ?? null });
          }
        },
      });
    },
    [apiBaseUrl, pollIntervalMs, stopPolling],
  );

  // The slot belongs to the lesson on screen: cancel any in-flight poll and start from the
  // build-time video (resolve it / show its failed state) — or idle when the course shipped none.
  // Depend on the artifact's scalars, not the object (Course re-serialises on every poll).
  const builtStatus = video?.status ?? null;
  const builtJobId = resolveJobId(video);
  useEffect(() => {
    jobIdRef.current = null;
    if (builtStatus === "ready" && builtJobId) {
      watch(builtJobId); // watch() sets the working state itself, then polls to ready
    } else if (builtStatus === "failed" && builtJobId) {
      // Resolve before failing: the re-attach probe (below) may surface a successful regenerate the
      // persisted (failed) artifact doesn't point to. Show a resolving state until the probe settles
      // — it falls back to the failed message only when there is genuinely no newer take, so the
      // slot never flashes "couldn't generate" before showing a good regenerate.
      setState({ phase: "working", status: "queued" });
    } else {
      setState({ phase: "idle" });
    }
    return stopPolling;
  }, [apiBaseUrl, courseId, lessonId, builtStatus, builtJobId, watch, stopPolling]);

  // Re-attach to an in-flight (re)generate the persisted artifact doesn't know about (Gap 1): ask
  // the server for the slot's live job — keyed by the source job we DO hold — and watch it. Calling
  // watch() aborts any poll the effect above started for the built artifact (shared controllerRef),
  // so a live regenerate always takes precedence over the stale built state — surviving a refresh /
  // navigate-away instead of the slot reverting to "couldn't generate".
  useEffect(() => {
    if (!builtJobId) return;
    const controller = new AbortController();
    void findActiveVideoJob(apiBaseUrl, builtJobId, controller.signal).then((view) => {
      if (controller.signal.aborted) return;
      if (view && view.job.id !== jobIdRef.current) {
        // A newer take the built artifact can't see — an in-flight job or a completed regenerate.
        // Skip when it's the job the first effect is already watching (don't double-poll a slot).
        watch(view.job.id);
      } else if (!view && builtStatus === "failed") {
        // No live job and no successful take: the slot genuinely failed. Show it now — the resolving
        // state above only deferred the message until this probe settled.
        setState({ phase: "failed", jobId: builtJobId, error: null });
      }
    });
    return () => controller.abort();
  }, [apiBaseUrl, courseId, lessonId, builtJobId, builtStatus, watch]);

  const generate = useCallback(() => {
    stopPolling();
    setState({ phase: "working", status: "queued" });
    void enqueueLessonVideo(apiBaseUrl, courseId, lessonId).then((result) => {
      switch (result.kind) {
        case "accepted":
          watch(result.view.job.id);
          break;
        case "keyless":
          setState({ phase: "keyless", detail: result.detail });
          break;
        case "unavailable":
          setState({ phase: "unavailable" });
          break;
        case "error":
          setState({ phase: "failed", jobId: null });
          break;
      }
    });
  }, [apiBaseUrl, courseId, lessonId, watch, stopPolling]);

  const regenerate = useCallback(
    (mode: RegenerateMode) => {
      const jobId = jobIdRef.current;
      if (!jobId) {
        generate(); // no source job (the enqueue itself failed) → just start fresh
        return;
      }
      stopPolling();
      setState({ phase: "working", status: "queued" });
      void regenerateVideo(apiBaseUrl, jobId, mode).then((result) => {
        switch (result.kind) {
          case "accepted":
            watch(result.view.job.id);
            break;
          case "disabled":
            setState({ phase: "unavailable" });
            break;
          case "conflict":
          case "error":
            setState({ phase: "failed", jobId });
            break;
        }
      });
    },
    [apiBaseUrl, generate, watch, stopPolling],
  );

  // Re-mint the ready job's short-lived signed URLs (they expire ~1h after the slot resolved). The
  // player calls this when its <video> fails to load the expired URL; we re-fetch the same job and
  // swap fresh URLs into the ready state, which remounts the player on the live URL — no reload.
  const refresh = useCallback(async () => {
    const jobId = jobIdRef.current;
    if (!jobId) return;
    const fresh = await fetchFreshPlaybackUrls(apiBaseUrl, jobId);
    if (!fresh || jobIdRef.current !== jobId) return; // gone, not ready, or the lesson moved on
    setState((prev) =>
      prev.phase === "ready" && prev.jobId === jobId
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

  return { state, generate, regenerate, refresh };
}
