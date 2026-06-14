import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchVideoJob,
  pollVideoJob,
  regenerateVideo,
  type RegenerateMode,
  type VideoJobStatus,
} from "../lib/videoJobs";
import type { VideoArtifact } from "../types/course";

export const COURSE_VIDEO_POLL_INTERVAL_MS = 2500;

/** What the Overview section knows about one course-level video. A build-time artifact is already
 *  terminal in the payload, so the resting states are ready / failed; `working` appears only while a
 *  regenerate (V6) the user triggered is in flight. */
export type CourseVideoState =
  | { phase: "absent" }
  | { phase: "loading" }
  | { phase: "working"; status: VideoJobStatus }
  | { phase: "ready"; videoUrl: string; posterUrl: string | null; captionsUrl: string | null }
  | { phase: "failed" };

/** Resolve a course video's playable state from its payload artifact, and let the reader regenerate
 *  it (explainer-video V5 + V6).
 *
 *  The build already rendered (or degraded) these, so a READY artifact carries `provenance.jobId`,
 *  exchanged for short-lived signed URLs via `GET /api/videos/{jobId}`. `regenerate(mode)` re-runs
 *  the artifact's job (READY *or* FAILED — both carry `jobId`) and polls the new job to a verdict,
 *  so a failed course video gets a retry path the published payload can't otherwise offer. */
export function useCourseVideo(
  apiBaseUrl: string | undefined,
  artifact: VideoArtifact | null | undefined,
  pollIntervalMs: number = COURSE_VIDEO_POLL_INTERVAL_MS,
): { state: CourseVideoState; regenerate: (mode: RegenerateMode) => void } {
  // Depend on scalars (status + jobId), not the artifact object — Course is re-serialised on every
  // poll, so a new object reference each render would re-fire the fetch even when nothing changed.
  const status = artifact?.status ?? null;
  const jobId = artifact ? (artifact.provenance?.jobId ?? artifact.jobId ?? null) : null;
  const readyJobId = status === "ready" ? jobId : null;
  const [state, setState] = useState<CourseVideoState>(() =>
    initialState(apiBaseUrl, status, readyJobId),
  );
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    controllerRef.current?.abort();
    if (status !== "ready" || !readyJobId || !apiBaseUrl) {
      setState(initialState(apiBaseUrl, status, readyJobId)); // absent or failed — nothing to fetch
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ phase: "loading" });
    void fetchVideoJob(apiBaseUrl, readyJobId, controller.signal).then((view) => {
      if (controller.signal.aborted) return;
      setState(toCourseVideoState(view?.videoUrl ? view : null));
    });
    return () => controller.abort();
  }, [apiBaseUrl, readyJobId, status]);

  const regenerate = useCallback(
    (mode: RegenerateMode) => {
      if (!apiBaseUrl || !jobId) return;
      controllerRef.current?.abort();
      setState({ phase: "working", status: "queued" });
      void regenerateVideo(apiBaseUrl, jobId, mode).then((result) => {
        if (result.kind !== "accepted") {
          setState({ phase: "failed" });
          return;
        }
        const controller = new AbortController();
        controllerRef.current = controller;
        void pollVideoJob(apiBaseUrl, result.view.job.id, {
          signal: controller.signal,
          intervalMs: pollIntervalMs,
          onWorking: (workingStatus) => setState({ phase: "working", status: workingStatus }),
          onSettled: (view) => setState(toCourseVideoState(view.videoUrl ? view : null)),
        });
      });
    },
    [apiBaseUrl, jobId, pollIntervalMs],
  );

  return { state, regenerate };
}

function toCourseVideoState(
  view: {
    videoUrl: string | null;
    posterUrl: string | null;
    captionsUrl: string | null;
  } | null,
): CourseVideoState {
  return view?.videoUrl
    ? {
        phase: "ready",
        videoUrl: view.videoUrl,
        posterUrl: view.posterUrl,
        captionsUrl: view.captionsUrl,
      }
    : { phase: "failed" };
}

function initialState(
  apiBaseUrl: string | undefined,
  status: VideoArtifact["status"] | null,
  jobId: string | null,
): CourseVideoState {
  if (status === null) return { phase: "absent" };
  // Not READY, no resolvable jobId, or no api base to fetch from → the honest failed state. A
  // resolvable READY artifact starts loading until the signed URL comes back (no broken-player flash).
  if (status !== "ready" || !jobId || !apiBaseUrl) return { phase: "failed" };
  return { phase: "loading" };
}
