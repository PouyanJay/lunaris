import { useEffect, useState } from "react";

import {
  fetchCoverJob,
  isCoverTerminal,
  pollCoverJob,
  resolveCoverJobId,
  type CoverJobStatus,
} from "../lib/coverJobs";
import type { CoverArtifact } from "../types/course";

export const COURSE_COVER_POLL_INTERVAL_MS = 3000;

/** What a surface knows about a course's AI cover, resolved from its payload artifact.
 *
 *  - `fallback` — no on-brand image to show (keyless account, a failed/cancelled cover, or none):
 *    the surface renders the **Typographic** cover. This is the resting state, NOT the constellation.
 *  - `generating` — a cover is in flight (the payload carries a non-terminal artifact): the surface
 *    shows the constellation as the LOADING state and this hook polls until it settles.
 *  - `image` — a READY cover whose short-lived signed URL resolved: the surface renders the image. */
export type CourseCoverState =
  | { phase: "fallback" }
  | { phase: "generating"; status: CoverJobStatus }
  | { phase: "image"; imageUrl: string };

/** Resolve a course's cover to a renderable state (course-cover-images T9).
 *
 *  A READY artifact carries a ``jobId`` handle (never a raw URL — URLs expire), exchanged for a
 *  short-lived signed URL via ``GET /api/covers/{jobId}``; a non-terminal artifact is polled to its
 *  verdict so a cover that finishes while the reader watches swaps in without a refresh. Everything
 *  else — no artifact, a FAILED/CANCELLED one, an account with no OpenAI key (which never enqueues a
 *  cover, so its artifact is absent) — resolves to ``fallback`` (the Typographic cover). Depends on
 *  the scalar ``status`` + ``jobId`` (not the artifact object), so a course re-serialised on each
 *  poll doesn't re-fire the fetch when nothing changed. */
export function useCourseCover(
  apiBaseUrl: string | undefined,
  artifact: CoverArtifact | null | undefined,
  pollIntervalMs: number = COURSE_COVER_POLL_INTERVAL_MS,
): { state: CourseCoverState } {
  const status = artifact?.status ?? null;
  const jobId = resolveCoverJobId(artifact);
  const [state, setState] = useState<CourseCoverState>({ phase: "fallback" });

  useEffect(() => {
    // No key / no cover / a settled non-READY cover → the Typographic fallback, no fetch.
    if (!apiBaseUrl || !jobId || status === null || status === "failed" || status === "cancelled") {
      setState({ phase: "fallback" });
      return;
    }
    const controller = new AbortController();

    if (status === "ready") {
      setState({ phase: "generating", status });
      void fetchCoverJob(apiBaseUrl, jobId, controller.signal).then((view) => {
        if (controller.signal.aborted) return;
        setState(
          view?.imageUrl ? { phase: "image", imageUrl: view.imageUrl } : { phase: "fallback" },
        );
      });
      return () => controller.abort();
    }

    // A non-terminal (in-flight) cover: show the constellation loading state and poll to a verdict.
    setState({ phase: "generating", status });
    void pollCoverJob(apiBaseUrl, jobId, {
      signal: controller.signal,
      intervalMs: pollIntervalMs,
      onWorking: (working) => {
        if (!controller.signal.aborted) setState({ phase: "generating", status: working });
      },
      onSettled: (view) => {
        if (controller.signal.aborted) return;
        const settled = view.job.status;
        setState(
          settled === "ready" && view.imageUrl
            ? { phase: "image", imageUrl: view.imageUrl }
            : { phase: "fallback" },
        );
      },
    });
    return () => controller.abort();
  }, [apiBaseUrl, jobId, status, pollIntervalMs]);

  // A settled-but-not-ready status is defensively coerced to the fallback (the effect already does
  // this; the guard keeps the returned state honest if the artifact changes between renders).
  if (
    status !== null &&
    isCoverTerminal(status) &&
    status !== "ready" &&
    state.phase !== "fallback"
  ) {
    return { state: { phase: "fallback" } };
  }
  return { state };
}
