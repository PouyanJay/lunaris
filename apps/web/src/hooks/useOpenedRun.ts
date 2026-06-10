import { useCallback, useEffect, useRef, useState } from "react";

import { CourseLoadError, fetchCourseById } from "../lib/loadCourse";
import type { Course, CourseRun } from "../types/course";

export type OpenedRunState =
  | { status: "closed" }
  | { status: "loading"; courseId: string; topic: string }
  // A running run has no persisted course yet; show this instead of fetching (which 404s).
  // Carries runId so the canvas can cancel the in-flight build (cancellation is keyed by run_id).
  | { status: "building"; courseId: string; topic: string; runId: string }
  // runId is carried through (when the opening run had one) so the Build tab can replay this run's
  // persisted log; undefined when reopened without one → the replay shows "no build record".
  | { status: "ready"; courseId: string; course: Course; runId: string | undefined }
  | { status: "error"; courseId: string; topic: string; message: string };

/** What a caller needs to open a run: its course_id, a title, the run's status, and (for a running
 *  run) its run_id so the building view can cancel the in-flight build. `runId` is optional because
 *  the internal reopen of an already-loaded course doesn't carry one and never needs it (it fetches
 *  rather than entering the building branch). */
type OpenableRun = Pick<CourseRun, "id" | "topic" | "status"> & { runId?: string };

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

/** How often an opened, still-building run re-checks for its finished course, so the canvas advances
 *  to the built course on its own when the run completes — no manual "Check again" needed. */
export const OPENED_RUN_RECHECK_INTERVAL_MS = 3000;

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
    (
      courseId: string,
      topic: string,
      runId: string | undefined,
      onNotFound: (error: CourseLoadError) => void,
      // A quiet load skips the `loading` flip — used by the background recheck poll, so a
      // still-building run's live timeline isn't unmounted to a skeleton on every tick.
      quiet = false,
    ) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      if (!quiet) setState({ status: "loading", courseId, topic });

      fetchCourseById(apiBaseUrl, courseId, controller.signal)
        .then((course) => {
          if (!controller.signal.aborted) setState({ status: "ready", courseId, course, runId });
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
        // No fetch: a running run's course isn't on disk until the build finishes. A running run
        // always carries a run_id (it comes from the run history); the fallback never triggers.
        controllerRef.current?.abort();
        setState({
          status: "building",
          courseId: run.id,
          topic: run.topic,
          runId: run.runId ?? "",
        });
        return;
      }
      // A completed/failed run whose course is gone (404) is a real error — surface the reason.
      load(run.id, run.topic, run.runId, (error) =>
        setState({ status: "error", courseId: run.id, topic: run.topic, message: error.message }),
      );
    },
    [load],
  );

  const recheck = useCallback(() => {
    const current = stateRef.current;
    if (current.status !== "building") return;
    const { courseId, topic, runId } = current;
    // A 404 means the build still hasn't persisted its course → stay building, not an error. Quiet,
    // so re-checking never flashes the loading skeleton over the live timeline (it flips only on a
    // real outcome: the finished course, or a hard error).
    load(
      courseId,
      topic,
      runId,
      () => setState({ status: "building", courseId, topic, runId }),
      true,
    );
  }, [load]);

  const close = useCallback(() => {
    controllerRef.current?.abort();
    setState({ status: "closed" });
  }, []);

  // While a still-building run is open, poll for its finished course so the canvas advances on its
  // own when the run completes — no manual re-check. Keyed on the building course_id (a stable value
  // for the run), so the interval is created once when building starts and cleared when it ends.
  const buildingCourseId = state.status === "building" ? state.courseId : null;
  useEffect(() => {
    if (!buildingCourseId) return undefined;
    const interval = setInterval(recheck, OPENED_RUN_RECHECK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [buildingCourseId, recheck]);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  return { state, open, recheck, close };
}
