import { useEffect, useState } from "react";

import { fetchCourseById } from "../lib/loadCourse";
import { fetchCourseProgress } from "../lib/progress";
import { resolveResumePoint, type ResumePoint } from "../lib/resumeLesson";

/** The resume enrichment for Home's continue-learning hero. The hero renders from the course
 *  summary immediately; this loads the one course + its progress to add "Lesson N of M", the
 *  next-up line, and a deep-link resume. `error` degrades the hero to summary-only (resume via
 *  the Overview tab). */
export type ContinueState =
  | { status: "loading" }
  | { status: "ready"; resume: ResumePoint | null }
  | { status: "error" };

/**
 * Loads the resume point for one in-progress course (the Home hero). Null `courseId` (no
 * in-progress course) skips the fetch. Aborts in-flight requests on unmount / course change. The
 * progress read is best-effort — a failure still resolves a resume point from the course itself
 * (first unfinished lesson); only a course-fetch failure surfaces as `error`.
 */
export function useContinueLearning(
  apiBaseUrl: string,
  courseId: string | null,
): ContinueState | null {
  const [state, setState] = useState<ContinueState | null>(courseId ? { status: "loading" } : null);

  useEffect(() => {
    if (!courseId) {
      setState(null);
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading" });
    Promise.all([
      fetchCourseById(apiBaseUrl, courseId, controller.signal),
      fetchCourseProgress(apiBaseUrl, courseId, controller.signal).catch(() => null),
    ])
      .then(([course, progress]) => {
        if (controller.signal.aborted) return;
        setState({ status: "ready", resume: resolveResumePoint(course, progress) });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setState({ status: "error" });
      });
    return () => controller.abort();
  }, [apiBaseUrl, courseId]);

  return state;
}
