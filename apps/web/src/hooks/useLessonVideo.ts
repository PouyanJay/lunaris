import { useCallback, useEffect, useRef, useState } from "react";

import {
  enqueueLessonVideo,
  fetchVideoJob,
  type VideoJobStatus,
  type VideoJobView,
} from "../lib/videoJobs";

export const VIDEO_POLL_INTERVAL_MS = 2500;

/** The hero slot's whole state machine, one discriminated union. */
export type LessonVideoState =
  | { phase: "idle" }
  | { phase: "working"; status: VideoJobStatus }
  | { phase: "ready"; videoUrl: string; posterUrl: string | null; captionsUrl: string | null }
  | { phase: "failed" }
  | { phase: "keyless"; detail: string }
  | { phase: "unavailable" };

const TERMINAL: ReadonlySet<VideoJobStatus> = new Set(["ready", "failed"]);

/** Drives one lesson's video generation: `generate()` enqueues, then the hook polls the job until
 *  it settles (the keyless-readiness polling shape: setTimeout chain + AbortController, stopped on
 *  unmount or lesson change). State resets when the lesson changes — the slot always describes the
 *  lesson on screen. V0 keeps the job binding in memory only; reloading the page returns to idle
 *  (the build-time stitch that persists lesson↔video lands in V4). */
export function useLessonVideo(
  apiBaseUrl: string,
  courseId: string,
  lessonId: string,
  pollIntervalMs: number = VIDEO_POLL_INTERVAL_MS,
): { state: LessonVideoState; generate: () => void } {
  const [state, setState] = useState<LessonVideoState>({ phase: "idle" });
  const controllerRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const stopPolling = useCallback(() => {
    controllerRef.current?.abort();
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  // A lesson change makes the slot the new lesson's: cancel any in-flight poll, back to idle.
  useEffect(() => {
    setState({ phase: "idle" });
    return stopPolling;
  }, [apiBaseUrl, courseId, lessonId, stopPolling]);

  const settle = useCallback((view: VideoJobView) => {
    if (view.job.status === "ready" && view.videoUrl) {
      setState({
        phase: "ready",
        videoUrl: view.videoUrl,
        posterUrl: view.posterUrl,
        captionsUrl: view.captionsUrl,
      });
    } else {
      setState({ phase: "failed" });
    }
  }, []);

  const poll = useCallback(
    (jobId: string) => {
      const controller = new AbortController();
      controllerRef.current = controller;
      const tick = async (): Promise<void> => {
        const view = await fetchVideoJob(apiBaseUrl, jobId, controller.signal);
        if (controller.signal.aborted) return;
        if (view === null) {
          // Retry-forever by design: a missed tick is transient (network blip, token refresh),
          // and the AbortController fired on navigation/lesson-change is the intended
          // termination — a bounded backoff would strand a slow job as "working" forever.
          timerRef.current = setTimeout(tick, pollIntervalMs);
          return;
        }
        if (TERMINAL.has(view.job.status)) {
          settle(view);
          return;
        }
        setState({ phase: "working", status: view.job.status });
        timerRef.current = setTimeout(tick, pollIntervalMs);
      };
      void tick();
    },
    [apiBaseUrl, pollIntervalMs, settle],
  );

  const generate = useCallback(() => {
    stopPolling();
    setState({ phase: "working", status: "queued" });
    void enqueueLessonVideo(apiBaseUrl, courseId, lessonId).then((result) => {
      switch (result.kind) {
        case "accepted":
          poll(result.view.job.id);
          break;
        case "keyless":
          setState({ phase: "keyless", detail: result.detail });
          break;
        case "unavailable":
          setState({ phase: "unavailable" });
          break;
        case "error":
          setState({ phase: "failed" });
          break;
      }
    });
  }, [apiBaseUrl, courseId, lessonId, poll, stopPolling]);

  return { state, generate };
}
