from collections.abc import Sequence

from lunaris_runtime.schema import CostEvent, CostSubjectType

from .persistence_error import PersistenceError


class InMemoryCostEventStore:
    """In-process cost ledger — the no-key/CI fallback and the test stub.

    Events live only for the process lifetime; durable, cross-machine drill-through requires the
    Supabase-backed store. Wired as a process-wide singleton so a build's cost writes and a later
    ``GET .../cost`` read share one ledger. Events are kept per subject — ``(subject_type,
    subject_id)``, the rollup key — and returned ordered by ``(run_id, seq)`` so the drill-through
    is deterministic regardless of insertion batching or which run/job produced them.
    """

    def __init__(self) -> None:
        self._events: dict[tuple[CostSubjectType, str], list[CostEvent]] = {}
        # The owner per subject (per-user scoping). All of a subject's cost events share one owner
        # (one course or graph, one user), so keying by subject suffices; kept parallel so
        # CostEvent's wire shape stays clean.
        self._owners: dict[tuple[CostSubjectType, str], str | None] = {}

    async def append(self, *, events: Sequence[CostEvent], owner_id: str | None = None) -> None:
        # Mirror the DB's UNIQUE (run_id, seq) index: a (run_id, seq) a run already recorded is a
        # failed insert, not a silently-appended duplicate — so double-recording a build is
        # reproducible in tests / the keyless path, not only on Postgres.
        batch: set[tuple[str, int]] = set()
        for event in events:
            key = (event.run_id, event.seq)
            # Checked across every subject, not just this one: the DB's unique index is on
            # (run_id, seq) alone. Scoping the check to one subject would let the fake accept a
            # batch Postgres rejects — the divergence that makes a test double worse than useless.
            clash = key in batch or any(
                e.run_id == event.run_id and e.seq == event.seq
                for events_for_subject in self._events.values()
                for e in events_for_subject
            )
            if clash:
                raise PersistenceError(f"cost_events insert failed: duplicate (run_id, seq) {key}")
            batch.add(key)
        for event in events:
            self._events.setdefault(_subject_of(event), []).append(event)
            self._owners[_subject_of(event)] = owner_id

    async def list_for_subject(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> list[CostEvent]:
        subject = (subject_type, subject_id)
        if owner_id is not None and self._owners.get(subject) != owner_id:
            return []  # another user's ledger reads as empty
        return sorted(self._events.get(subject, []), key=lambda event: (event.run_id, event.seq))

    async def delete_for_subject(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> int:
        """Drop every cost event for a subject. Returns the number of rows removed (0 if none).

        A scoped caller (``owner_id`` set) only purges a subject they own; an unscoped caller purges
        it unconditionally.
        """
        subject = (subject_type, subject_id)
        if owner_id is not None and self._owners.get(subject) != owner_id:
            return 0
        removed = len(self._events.pop(subject, []))
        self._owners.pop(subject, None)
        return removed


def _subject_of(event: CostEvent) -> tuple[CostSubjectType, str]:
    """The rollup key an event belongs under. Both halves, always: a course id and a graph id come
    from different sequences and may collide, and merging two products' spend is unrecoverable in an
    append-only ledger."""
    return (event.subject_type, event.subject_id)
