from collections.abc import Sequence

from lunaris_runtime.schema import RunEvent


class InMemoryRunEventStore:
    """In-process build-log store — the no-key/CI fallback and the test stub.

    Logs live only for the process lifetime (lost on restart); durable, cross-machine replay
    requires the Supabase-backed store. Wired as a process-wide singleton at the composition root so
    a build's writes and a later replay read share one log. Events are kept per ``run_id`` in append
    order and returned by ascending ``seq`` (the caller-assigned emission order), so replay is
    deterministic regardless of insertion batching.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[RunEvent]] = {}
        # The owner per run_id (Phase 2). All of a run's events share one owner (one build, one
        # user), so keying by run_id suffices; kept parallel so RunEvent's wire shape is untouched.
        self._owners: dict[str, str | None] = {}

    async def append(self, *, events: Sequence[RunEvent], owner_id: str | None = None) -> None:
        for event in events:
            self._events.setdefault(event.run_id, []).append(event)
            # All events in a batch share one run (one build, one user), so recording the owner
            # per run_id here is idempotent within the batch — kept in the loop to cover the
            # (defensive) case of a mixed-run batch rather than assuming events[0]'s run_id.
            self._owners[event.run_id] = owner_id

    async def list_for_run(self, *, run_id: str, owner_id: str | None = None) -> list[RunEvent]:
        if owner_id is not None and self._owners.get(run_id) != owner_id:
            return []  # another user's transcript reads as empty
        return sorted(self._events.get(run_id, []), key=lambda event: event.seq)

    async def delete_for_course(self, *, course_id: str, owner_id: str | None = None) -> int:
        """Drop every run's events for a course. Returns the number of rows removed (0 if none).

        A scoped caller (``owner_id`` set) only purges runs they own; an unscoped caller purges all.
        """
        removed = 0
        for run_id in list(self._events):
            if owner_id is not None and self._owners.get(run_id) != owner_id:
                continue
            kept = [event for event in self._events[run_id] if event.course_id != course_id]
            removed += len(self._events[run_id]) - len(kept)
            if kept:
                self._events[run_id] = kept
            else:
                del self._events[run_id]
                self._owners.pop(run_id, None)
        return removed
