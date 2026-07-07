import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";

import type { OpenedRun } from "./useOpenedRun";
import { coursePath, type ShellRoute } from "../lib/routes";
import type { CourseRun } from "../types/course";

interface CourseRoutingInputs {
  route: ShellRoute;
  /** The course this tab's own build stream is creating (streaming with a known id, or ready). */
  streamCourseId: string | undefined;
  /** The run-history rows, when loaded — they supply topic/status/runId for opens. */
  runs: CourseRun[] | null;
  opened: OpenedRun;
}

interface CourseRouting {
  /** The courseId named by the URL, when on a course route. */
  routedCourseId: string | null;
  /** Whether this tab's live stream owns the routed course's canvas. */
  liveMatchesRoute: boolean;
  /** Whether the live stream's course was already handed its URL — after that, home is the
   *  composer again (the finished course stays reachable at its own URL). */
  handedOff: boolean;
  /** Forget the handoff (call alongside the stream's reset, so the next build hands off anew). */
  clearHandoff: () => void;
}

/** The URL ⇄ course-state contract: syncs the opened-run flow to `/courses/:courseId` routes, and
 *  hands a live build's URL off to its course exactly once per stream (replace-navigation, so
 *  Back skips the transient composer state). */
export function useCourseRouting({
  route,
  streamCourseId,
  runs,
  opened,
}: CourseRoutingInputs): CourseRouting {
  const navigate = useNavigate();
  const routedCourseId = route.kind === "course" ? route.courseId : null;
  const liveMatchesRoute = routedCourseId !== null && streamCourseId === routedCourseId;

  // Hand off once per built course: after that, revisiting home renders the composer rather than
  // bouncing back or (worse) re-hosting the finished course on "/".
  const [handedOffCourseId, setHandedOffCourseId] = useState<string | undefined>(undefined);
  const handedOff = streamCourseId !== undefined && handedOffCourseId === streamCourseId;
  const clearHandoff = useCallback(() => setHandedOffCourseId(undefined), []);
  useEffect(() => {
    if (route.kind === "home" && streamCourseId && handedOffCourseId !== streamCourseId) {
      setHandedOffCourseId(streamCourseId);
      navigate(coursePath(streamCourseId), { replace: true });
    }
  }, [route.kind, streamCourseId, handedOffCourseId, navigate]);

  // The URL is the source of truth for which course is open. A run-history row supplies
  // topic/status/runId when it has the course; a cold deep-link falls back to a fetch by id
  // (a 404 lands on the opened-run error canvas). While the history is still loading, wait —
  // the effect re-fires when it resolves. Depend on narrow primitives (status + courseId), not
  // the state object: useOpenedRun's building poll re-creates the object every tick.
  const { open: openRun, close: closeRun } = opened;
  const openedStatus = opened.state.status;
  const openedCourseId = opened.state.status !== "closed" ? opened.state.courseId : null;
  useEffect(() => {
    if (!routedCourseId || liveMatchesRoute) {
      if (openedStatus !== "closed") closeRun();
      return;
    }
    if (openedStatus !== "closed" && openedCourseId === routedCourseId) return;
    const row = runs?.find((run) => run.id === routedCourseId);
    if (row) openRun(row);
    else if (runs) openRun({ id: routedCourseId, topic: "Course", status: "completed" });
  }, [routedCourseId, liveMatchesRoute, runs, openedStatus, openedCourseId, openRun, closeRun]);

  return { routedCourseId, liveMatchesRoute, handedOff, clearHandoff };
}
