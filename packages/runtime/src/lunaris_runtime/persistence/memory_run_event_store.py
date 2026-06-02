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

    async def append(self, *, events: Sequence[RunEvent]) -> None:
        for event in events:
            self._events.setdefault(event.run_id, []).append(event)

    async def list_for_run(self, *, run_id: str) -> list[RunEvent]:
        return sorted(self._events.get(run_id, []), key=lambda event: event.seq)

    async def delete_for_course(self, *, course_id: str) -> int:
        """Drop every run's events for a course. Returns the number of rows removed (0 if none)."""
        removed = 0
        for run_id in list(self._events):
            kept = [event for event in self._events[run_id] if event.course_id != course_id]
            removed += len(self._events[run_id]) - len(kept)
            if kept:
                self._events[run_id] = kept
            else:
                del self._events[run_id]
        return removed
