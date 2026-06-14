import { useCallback, useEffect, useRef, useState } from "react";

import {
  enqueueLessonVideo,
  pollVideoJob,
  regenerateVideo,
  type RegenerateMode,
  type VideoJobStatus,
} from "../lib/videoJobs";

export const VIDEO_POLL_INTERVAL_MS = 2500;

/** The hero slot's whole state machine, one discriminated union. `ready`/`failed` carry the source
 *  `jobId` so the regenerate menu (V6) can re-run them; `failed` is `null` only when the enqueue
 *  itself never produced a job. */
export type LessonVideoState =
  | { phase: "idle" }
  | { phase: "working"; status: VideoJobStatus }
  | {
      phase: "ready";
      jobId: string;
      videoUrl: string;
      posterUrl: string | null;
      captionsUrl: string | null;
    }
  | { phase: "failed"; jobId: string | null }
  | { phase: "keyless"; detail: string }
  | { phase: "unavailable" };

/** Drives one lesson's video generation: `generate()` enqueues and the hook polls the job until it
 *  settles; `regenerate(mode)` re-runs the last job through the menu (V6). State resets when the
 *  lesson changes — the slot always describes the lesson on screen. The job binding lives in memory
 *  only (V0): reloading the page returns to idle. */
export function useLessonVideo(
  apiBaseUrl: string,
  courseId: string,
  lessonId: string,
  pollIntervalMs: number = VIDEO_POLL_INTERVAL_MS,
): {
  state: LessonVideoState;
  generate: () => void;
  regenerate: (mode: RegenerateMode) => void;
} {
  const [state, setState] = useState<LessonVideoState>({ phase: "idle" });
  const controllerRef = useRef<AbortController | null>(null);
  const jobIdRef = useRef<string | null>(null);

  const stopPolling = useCallback(() => controllerRef.current?.abort(), []);

  // A lesson change makes the slot the new lesson's: cancel any in-flight poll, back to idle.
  useEffect(() => {
    setState({ phase: "idle" });
    jobIdRef.current = null;
    return stopPolling;
  }, [apiBaseUrl, courseId, lessonId, stopPolling]);

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
            });
          } else {
            setState({ phase: "failed", jobId });
          }
        },
      });
    },
    [apiBaseUrl, pollIntervalMs, stopPolling],
  );

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
