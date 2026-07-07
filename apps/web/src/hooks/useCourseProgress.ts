import { useCallback, useEffect, useState } from "react";

import {
  type CourseProgress,
  fetchCourseProgress,
  type LessonState,
  putLessonProgress,
  putObjectiveProgress,
} from "../lib/progress";

interface CourseProgressHandle {
  /** Null while loading, on error, and offline — the reader shows no progress chrome. */
  progress: CourseProgress | null;
  reload: () => void;
  /** Optimistically mark/un-mark one module objective, then persist (reconciles on failure). */
  markObjective: (moduleId: string, objectiveIndex: number, understood: boolean) => void;
  /** Optimistically advance a lesson's state, then persist (reconciles on failure). */
  markLesson: (lessonId: string, state: LessonState) => void;
}

/** Tracks the learner's progress on one course. Best-effort by design: reading must never block
 *  on the progress substrate, so failures leave `progress` null (no chrome) and failed writes
 *  reconcile by refetching. An empty `apiBaseUrl` (the offline seed surface) disables it. */
export function useCourseProgress(apiBaseUrl: string, courseId: string): CourseProgressHandle {
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

  const markObjective = useCallback(
    (moduleId: string, objectiveIndex: number, understood: boolean) => {
      setProgress((current) => {
        if (!current) return current;
        const others = current.objectives.filter(
          (mark) => !(mark.moduleId === moduleId && mark.objectiveIndex === objectiveIndex),
        );
        return {
          ...current,
          objectives: understood
            ? [...others, { moduleId, objectiveIndex, understoodAt: new Date().toISOString() }]
            : others,
        };
      });
      putObjectiveProgress(apiBaseUrl, courseId, { moduleId, objectiveIndex, understood }).catch(
        reload,
      );
    },
    [apiBaseUrl, courseId, reload],
  );

  const markLesson = useCallback(
    (lessonId: string, state: LessonState) => {
      setProgress((current) => {
        if (!current) return current;
        const others = current.lessons.filter((mark) => mark.lessonId !== lessonId);
        return {
          ...current,
          lessons: [...others, { lessonId, state, updatedAt: new Date().toISOString() }],
        };
      });
      putLessonProgress(apiBaseUrl, courseId, { lessonId, state }).catch(reload);
    },
    [apiBaseUrl, courseId, reload],
  );

  return { progress, reload, markObjective, markLesson };
}
