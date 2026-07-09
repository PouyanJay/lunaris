import { ConfirmDialog } from "../overlays/ConfirmDialog";
import type { CourseDeletion } from "../../hooks/useCourseDeletion";

/** The one confirm dialog for deleting a course, shared by every surface that offers delete — the
 *  library grid, Home, and the course Overview. Driven by a `useCourseDeletion` instance so the
 *  irreversible-purge copy (and its full-purge honesty about what's removed) lives in one place. */
export function DeleteCourseDialog({
  deletion,
  confirmLabel = "Delete",
}: {
  deletion: CourseDeletion;
  confirmLabel?: string;
}) {
  return (
    <ConfirmDialog
      open={deletion.pending !== null}
      title="Delete this course?"
      description={
        deletion.pending
          ? `“${deletion.pending.topic}” and everything about it — lessons, videos, your ` +
            "progress, bookmarks, and notes — will be permanently deleted. This can’t be undone."
          : ""
      }
      confirmLabel={confirmLabel}
      pendingLabel="Deleting…"
      danger
      pending={deletion.isDeleting}
      errorMessage={deletion.error}
      onConfirm={deletion.confirm}
      onCancel={deletion.cancel}
    />
  );
}
