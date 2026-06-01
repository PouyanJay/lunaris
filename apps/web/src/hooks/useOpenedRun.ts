import { useCallback, useEffect, useRef, useState } from "react";

import { CourseLoadError, fetchCourseById } from "../lib/loadCourse";
import type { Course, CourseRun } from "../types/course";

export type OpenedRunState =
  | { status: "closed" }
  | { status: "loading"; courseId: string; topic: string }
  // A running run has no persisted course yet; show this instead of fetching (which 404s).
  | { status: "building"; courseId: string; topic: string }
  | { status: "ready"; courseId: string; course: Course }
  | { status: "error"; courseId: string; topic: string; message: string };

/** The minimum a caller needs to open a run: its course_id, a title for the header, and the run's
 *  status — a running run has no persisted course yet, so we show "still building" rather than
 *  fetching and rendering a broken-looking 404. */
type OpenableRun = Pick<CourseRun, "id" | "topic" | "status">;

interface OpenedRun {
  state: OpenedRunState;
  /** Open a run from the sidebar: a completed/failed run is fetched by course_id; a running run
   *  shows the building state directly (its course isn't persisted until the run finishes). */
  open: (run: OpenableRun) => void;
  /** Re-check a still-building run: re-fetch its course. Once the build has finished it opens;
   *  while it's still running (404) it stays in the building state. No-op unless one is building. */
  recheck: () => void;
  /** Return to the build surface (close the opened run). */
  close: () => void;
}

/**
 * Opens a historical run's course in the canvas: closed → loading → ready (the course) or error,
 * with a `building` state for a run still in progress. Each open/recheck aborts any prior in-flight
 * fetch; the controller is aborted on unmount, so a slow fetch never lands after the view changed.
 * `topic` is carried through loading/building/error so the canvas header has a title before the
 * course arrives.
 */
export function useOpenedRun(apiBaseUrl: string): OpenedRun {
  const [state, setState] = useState<OpenedRunState>({ status: "closed" });
  const controllerRef = useRef<AbortController | null>(null);
  // Mirror the latest state so `recheck` can read the open run without depending on `state` — that
  // dependency would churn its identity on every transition, including the loading flip it triggers.
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // Fetch a course by id and route the outcome. `onNotFound` decides what an absent course (HTTP
  // 404) means at this call site: opening a completed run treats it as a genuine error; re-checking
  // a running run treats it as "still building". Non-404 failures are always an error.
  const load = useCallback(
    (courseId: string, topic: string, onNotFound: (error: CourseLoadError) => void) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ status: "loading", courseId, topic });

      fetchCourseById(apiBaseUrl, courseId, controller.signal)
        .then((course) => {
          if (!controller.signal.aborted) setState({ status: "ready", courseId, course });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          if (error instanceof CourseLoadError && error.status === 404) {
            onNotFound(error);
            return;
          }
          const message =
            error instanceof CourseLoadError ? error.message : "Couldn't open this course.";
          setState({ status: "error", courseId, topic, message });
        });
    },
    [apiBaseUrl],
  );

  const open = useCallback(
    (run: OpenableRun) => {
      if (run.status === "running") {
        // No fetch: a running run's course isn't on disk until the build finishes.
        controllerRef.current?.abort();
        setState({ status: "building", courseId: run.id, topic: run.topic });
        return;
      }
      // A completed/failed run whose course is gone (404) is a real error — surface the reason.
      load(run.id, run.topic, (error) =>
        setState({ status: "error", courseId: run.id, topic: run.topic, message: error.message }),
      );
    },
    [load],
  );

  const recheck = useCallback(() => {
    const current = stateRef.current;
    if (current.status !== "building") return;
    const { courseId, topic } = current;
    // A 404 means the build still hasn't persisted its course → stay building, not an error.
    load(courseId, topic, () => setState({ status: "building", courseId, topic }));
  }, [load]);

  const close = useCallback(() => {
    controllerRef.current?.abort();
    setState({ status: "closed" });
  }, []);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  return { state, open, recheck, close };
}
