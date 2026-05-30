import { useCallback, useEffect, useState } from "react";

import { CourseLoadError, resolveCourse } from "../lib/loadCourse";
import type { Course } from "../types/course";

export type CourseState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; course: Course };

const MIN_VISIBLE_MS = 250; // keep the skeleton up briefly so a fast load doesn't flash

/** Loads the course-object, exposing a single state machine for the four data states and a
 *  reload action. Aborts in-flight requests on unmount / reload. */
export function useCourse(): { state: CourseState; reload: () => void } {
  const [state, setState] = useState<CourseState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const startedAt = Date.now();

    resolveCourse(controller.signal)
      .then(async (course) => {
        const elapsed = Date.now() - startedAt;
        if (elapsed < MIN_VISIBLE_MS) {
          await new Promise((resolve) => setTimeout(resolve, MIN_VISIBLE_MS - elapsed));
        }
        if (!controller.signal.aborted) setState({ status: "ready", course });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof CourseLoadError
            ? error.message
            : "An unexpected error occurred while loading the course.";
        setState({ status: "error", message });
      });

    return () => controller.abort();
  }, [attempt]);

  return { state, reload };
}
