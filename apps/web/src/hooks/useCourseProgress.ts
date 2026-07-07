import { useCallback, useEffect, useState } from "react";

import { type CourseProgress, fetchCourseProgress } from "../lib/progress";

/** Tracks the learner's progress on one course, with a `reload` for after a write. Best-effort:
 *  while loading or on error `progress` is null and the reader simply shows no progress chrome —
 *  reading must never block on the progress substrate. An empty `apiBaseUrl` (the offline seed
 *  surface) skips fetching entirely. */
export function useCourseProgress(
  apiBaseUrl: string,
  courseId: string,
): { progress: CourseProgress | null; reload: () => void } {
  const [progress, setProgress] = useState<CourseProgress | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    // A course switch must not show the previous course's counters while the fetch is in flight.
    setProgress(null);
    if (!apiBaseUrl) return undefined;
    const controller = new AbortController();
    fetchCourseProgress(apiBaseUrl, courseId, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) setProgress(next);
      })
      .catch(() => {
        /* best-effort — no progress chrome rather than a blocked reader */
      });
    return () => controller.abort();
  }, [apiBaseUrl, courseId, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { progress, reload };
}
