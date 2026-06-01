import { useCallback, useState } from "react";

import { deleteCourse } from "../lib/loadCourse";
import type { CourseRun } from "../types/course";
import type { OpenedRunState } from "./useOpenedRun";

interface DeleteRun {
  /** The run awaiting delete confirmation (drives the dialog), or null when none is pending. */
  pendingDelete: CourseRun | null;
  isDeleting: boolean;
  deleteError: string | null;
  /** Ask to delete a run — opens the confirm dialog. */
  request: (run: CourseRun) => void;
  /** Dismiss the dialog (a no-op while a delete is in flight). */
  cancel: () => void;
  /** Confirm: DELETE the course, then drop any open view of it and refresh the run history. */
  confirm: () => Promise<void>;
}

/** The delete-a-run workflow: a confirm-before dialog, the DELETE call, and the post-delete cleanup
 *  (close the canvas if the deleted run was open; refresh the history). Extracted from StudioApp so
 *  that component isn't a grab-bag of unrelated state. On failure (e.g. 409 still building) the
 *  dialog stays open carrying the reason. */
export function useDeleteRun(
  apiBaseUrl: string,
  openedState: OpenedRunState,
  closeOpenedRun: () => void,
  reloadRuns: () => void,
): DeleteRun {
  const [pendingDelete, setPendingDelete] = useState<CourseRun | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const request = useCallback((run: CourseRun) => {
    setPendingDelete(run);
    setDeleteError(null);
  }, []);

  const cancel = useCallback(() => {
    if (!isDeleting) setPendingDelete(null);
  }, [isDeleting]);

  const confirm = useCallback(async () => {
    if (pendingDelete === null) return;
    const run = pendingDelete;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteCourse(apiBaseUrl, run.id);
      if (openedState.status !== "closed" && openedState.courseId === run.id) closeOpenedRun();
      reloadRuns();
      setPendingDelete(null);
    } catch (error: unknown) {
      setDeleteError(error instanceof Error ? error.message : "Couldn’t delete this course.");
    } finally {
      setIsDeleting(false);
    }
  }, [apiBaseUrl, pendingDelete, openedState, closeOpenedRun, reloadRuns]);

  return { pendingDelete, isDeleting, deleteError, request, cancel, confirm };
}
