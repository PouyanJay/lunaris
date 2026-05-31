import { useCallback, useEffect, useRef, useState } from "react";

import { CourseLoadError, fetchCourseById } from "../lib/loadCourse";
import type { Course, CourseRun } from "../types/course";

export type OpenedRunState =
  | { status: "closed" }
  | { status: "loading"; courseId: string; topic: string }
  | { status: "ready"; courseId: string; course: Course }
  | { status: "error"; courseId: string; topic: string; message: string };

/** The minimum a caller needs to open a run: its course_id and a title for the header. */
type OpenableRun = Pick<CourseRun, "id" | "topic">;

interface OpenedRun {
  state: OpenedRunState;
  /** Open a run from the sidebar — fetches its course by id (course_id). */
  open: (run: OpenableRun) => void;
  /** Return to the build surface (close the opened run). */
  close: () => void;
}

/**
 * Opens a historical run's course in the canvas: closed → loading → ready (the course) or error.
 * Each open aborts any prior in-flight fetch; the controller is aborted on unmount, so a slow
 * fetch never lands after the view changed. `topic` is carried through loading/error so the canvas
 * header has a title before the course arrives.
 */
export function useOpenedRun(apiBaseUrl: string): OpenedRun {
  const [state, setState] = useState<OpenedRunState>({ status: "closed" });
  const controllerRef = useRef<AbortController | null>(null);

  const open = useCallback(
    (run: OpenableRun) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ status: "loading", courseId: run.id, topic: run.topic });

      fetchCourseById(apiBaseUrl, run.id, controller.signal)
        .then((course) => {
          if (!controller.signal.aborted) {
            setState({ status: "ready", courseId: run.id, course });
          }
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          const message =
            error instanceof CourseLoadError ? error.message : "Couldn't open this course.";
          setState({ status: "error", courseId: run.id, topic: run.topic, message });
        });
    },
    [apiBaseUrl],
  );

  const close = useCallback(() => {
    controllerRef.current?.abort();
    setState({ status: "closed" });
  }, []);

  useEffect(() => () => controllerRef.current?.abort(), []);

  return { state, open, close };
}
