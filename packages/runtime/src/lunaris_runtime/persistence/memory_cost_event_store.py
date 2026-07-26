from collections.abc import Sequence

from lunaris_runtime.schema import CostEvent

from .persistence_error import PersistenceError


class InMemoryCostEventStore:
    """In-process cost ledger — the no-key/CI fallback and the test stub.

    Events live only for the process lifetime; durable, cross-machine drill-through requires the
    Supabase-backed store. Wired as a process-wide singleton so a build's cost writes and a later
    ``GET .../cost`` read share one ledger. Events are kept per ``course_id`` (the rollup key) and
    returned ordered by ``(run_id, seq)`` so the drill-through is deterministic regardless of
    insertion batching or which run/job produced them.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[CostEvent]] = {}
        # The owner per course_id (per-user scoping). All of a course's cost events share one owner
        # (one course, one user), so keying by course_id suffices; kept parallel so CostEvent's wire
        # shape stays clean.
        self._owners: dict[str, str | None] = {}

    async def append(self, *, events: Sequence[CostEvent], owner_id: str | None = None) -> None:
        # Mirror the DB's UNIQUE (run_id, seq) index: a (run_id, seq) a run already recorded is a
        # failed insert, not a silently-appended duplicate — so double-recording a build is
        # reproducible in tests / the keyless path, not only on Postgres.
        batch: set[tuple[str, int]] = set()
        for event in events:
            key = (event.run_id, event.seq)
            existing = self._events.get(event.course_id, ())
            clash = key in batch or any(
                e.run_id == event.run_id and e.seq == event.seq for e in existing
            )
            if clash:
                raise PersistenceError(f"cost_events insert failed: duplicate (run_id, seq) {key}")
            batch.add(key)
        for event in events:
            self._events.setdefault(event.course_id, []).append(event)
            self._owners[event.course_id] = owner_id

    async def list_for_course(
        self, *, course_id: str, owner_id: str | None = None
    ) -> list[CostEvent]:
        if owner_id is not None and self._owners.get(course_id) != owner_id:
            return []  # another user's ledger reads as empty
        return sorted(self._events.get(course_id, []), key=lambda event: (event.run_id, event.seq))

    async def delete_for_course(self, *, course_id: str, owner_id: str | None = None) -> int:
        """Drop every cost event for a course. Returns the number of rows removed (0 if none).

        A scoped caller (``owner_id`` set) only purges a course they own; an unscoped caller purges
        it unconditionally.
        """
        if owner_id is not None and self._owners.get(course_id) != owner_id:
            return 0
        removed = len(self._events.pop(course_id, []))
        self._owners.pop(course_id, None)
        return removed
