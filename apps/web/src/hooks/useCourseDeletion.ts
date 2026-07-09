import { useCallback, useState } from "react";

import { deleteCourse } from "../lib/loadCourse";

/** The minimum a delete flow needs: the id to DELETE and the title to name in the confirm dialog. */
export interface DeletableCourse {
  id: string;
  topic: string;
}

export interface CourseDeletion {
  /** The course awaiting confirmation (drives the dialog), or null when none is pending. */
  pending: DeletableCourse | null;
  isDeleting: boolean;
  /** A human message when the DELETE failed (e.g. 409 still building); the dialog stays open. */
  error: string | null;
  /** Ask to delete a course — opens the confirm dialog. */
  request: (course: DeletableCourse) => void;
  /** Dismiss the dialog (a no-op while a delete is in flight). */
  cancel: () => void;
  /** Confirm: DELETE the course and its assets, then run `onDeleted` (e.g. reload the grid). */
  confirm: () => Promise<void>;
}

/** The confirm-before delete workflow for a course, shared by the library grid, Home, and the
 *  course Overview. On success it invokes `onDeleted(id)` (refresh a list, or leave the course);
 *  on failure the dialog stays open carrying the reason. Confirm-before, never optimistic — the
 *  purge is irreversible. */
export function useCourseDeletion(
  apiBaseUrl: string,
  onDeleted?: (courseId: string) => void,
): CourseDeletion {
  const [pending, setPending] = useState<DeletableCourse | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = useCallback((course: DeletableCourse) => {
    setPending(course);
    setError(null);
  }, []);

  const cancel = useCallback(() => {
    if (!isDeleting) setPending(null);
  }, [isDeleting]);

  const confirm = useCallback(async () => {
    if (pending === null) return;
    const { id } = pending;
    setIsDeleting(true);
    setError(null);
    try {
      await deleteCourse(apiBaseUrl, id);
      setPending(null);
      onDeleted?.(id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Couldn’t delete this course.");
    } finally {
      setIsDeleting(false);
    }
  }, [apiBaseUrl, pending, onDeleted]);

  return { pending, isDeleting, error, request, cancel, confirm };
}
