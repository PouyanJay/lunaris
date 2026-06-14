import { useEffect, useState } from "react";

import { fetchVideoJob } from "../lib/videoJobs";
import type { VideoArtifact } from "../types/course";

/** What the Overview section knows about one course-level video. A build-time artifact is already
 *  terminal in the payload, so there is no "working" state here (unlike the on-demand lesson hero):
 *  it is either ready (its signed URL resolved), still resolving that URL, or failed. */
export type CourseVideoState =
  | { phase: "absent" }
  | { phase: "loading" }
  | { phase: "ready"; videoUrl: string; posterUrl: string | null; captionsUrl: string | null }
  | { phase: "failed" };

/** Resolve a course video's playable state from its payload artifact (explainer-video V5).
 *
 *  The build already rendered (or degraded) these, so the artifact carries the verdict: a READY one
 *  carries ``provenance.jobId``, which we exchange for short-lived signed URLs via
 *  ``GET /api/videos/{jobId}`` (the same endpoint the lesson hero polls). A FAILED artifact — or a
 *  READY one whose URL can't be resolved (job swept, network, or no jobId) — degrades to ``failed``
 *  so the slot shows an honest "couldn't generate" rather than a broken player. ``absent`` (no
 *  artifact) lets the caller render no slot at all. */
export function useCourseVideo(
  apiBaseUrl: string | undefined,
  artifact: VideoArtifact | null | undefined,
): CourseVideoState {
  // Depend on scalars (status + jobId), not the artifact object — Course is re-serialised on every
  // poll, so a new object reference each render would re-fire the fetch even when nothing changed.
  const status = artifact?.status ?? null;
  const jobId = status === "ready" ? (artifact?.provenance?.jobId ?? null) : null;
  const [state, setState] = useState<CourseVideoState>(() =>
    initialState(apiBaseUrl, status, jobId),
  );

  useEffect(() => {
    if (status !== "ready" || !jobId || !apiBaseUrl) {
      setState(initialState(apiBaseUrl, status, jobId)); // absent or failed — nothing to fetch
      return;
    }
    const controller = new AbortController();
    setState({ phase: "loading" });
    void fetchVideoJob(apiBaseUrl, jobId, controller.signal).then((view) => {
      if (controller.signal.aborted) return;
      setState(
        view?.videoUrl
          ? {
              phase: "ready",
              videoUrl: view.videoUrl,
              posterUrl: view.posterUrl,
              captionsUrl: view.captionsUrl,
            }
          : { phase: "failed" },
      );
    });
    return () => controller.abort();
  }, [apiBaseUrl, jobId, status]);

  return state;
}

function initialState(
  apiBaseUrl: string | undefined,
  status: VideoArtifact["status"] | null,
  jobId: string | null,
): CourseVideoState {
  if (status === null) return { phase: "absent" };
  // Not READY, no resolvable jobId, or no api base to fetch from → the honest failed state. A
  // resolvable READY artifact starts in loading until the signed URL comes back (no broken-player flash).
  if (status !== "ready" || !jobId || !apiBaseUrl) return { phase: "failed" };
  return { phase: "loading" };
}
