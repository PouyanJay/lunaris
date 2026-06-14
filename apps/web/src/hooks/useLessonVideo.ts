import { useCallback, useEffect, useRef, useState } from "react";

import {
  enqueueLessonVideo,
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
  | { phase: "failed"; jobId: string | null }
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
            setState({ phase: "failed", jobId });
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
      setState({ phase: "working", status: "queued" });
      watch(builtJobId);
    } else if (builtStatus === "failed" && builtJobId) {
      setState({ phase: "failed", jobId: builtJobId });
    } else {
      setState({ phase: "idle" });
    }
    return stopPolling;
  }, [apiBaseUrl, courseId, lessonId, builtStatus, builtJobId, watch, stopPolling]);

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

  return { state, generate, regenerate };
}
