from typing import Protocol

from lunaris_runtime.schema import CostSubjectType, SubjectCost


class ISubjectCostStore(Protocol):
    """Persistence for the one-row-per-subject cost rollup — "this cost ~$X to build".

    The rollup twin of ``ICostEventStore`` (the ledger): where that keeps every paid call, this
    keeps the materialized total + breakdown the course Overview reads without scanning the ledger.
    ``upsert`` refreshes the row on the natural key (``(subject_type, subject_id)``) each time a job
    finishes and
    recomputes the total from the ledger — so re-recording is idempotent, never a duplicate. ``get``
    feeds ``GET /api/courses/{id}/cost`` (``None`` when the course has no metered cost yet — a
    pre-feature or still-building course). ``delete_for_subject`` drops the rollup when the
    subject itself is purged.

    ``owner_id`` (per-user scoping) is the authenticated caller's id: ``upsert`` stamps it, ``get``
    and ``delete_for_subject`` constrain to it (another user's rollup reads as ``None``). ``None``
    means unscoped — the auth-off / single-user path.

    Backend failures raise ``PersistenceError`` — the only store error callers may treat as
    best-effort; anything else is a bug and must surface.
    """

    async def upsert(self, *, cost: SubjectCost, owner_id: str | None = None) -> None: ...

    async def get(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> SubjectCost | None: ...

    async def delete_for_subject(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> int: ...
