from typing import Protocol

from lunaris_runtime.schema import CourseCost


class ICourseCostStore(Protocol):
    """Persistence for the one-row-per-course cost rollup — "this course cost ~$X to build".

    The rollup twin of ``ICostEventStore`` (the ledger): where that keeps every paid call, this
    keeps the materialized total + breakdown the course Overview reads without scanning the ledger.
    ``upsert`` refreshes the row on the natural key (``course_id``) each time a job finishes and
    recomputes the total from the ledger — so re-recording is idempotent, never a duplicate. ``get``
    feeds ``GET /api/courses/{id}/cost`` (``None`` when the course has no metered cost yet — a
    pre-feature or still-building course). ``delete_for_course`` drops the rollup on a full course
    delete.

    ``owner_id`` (per-user scoping) is the authenticated caller's id: ``upsert`` stamps it, ``get``
    and ``delete_for_course`` constrain to it (another user's rollup reads as ``None``). ``None``
    means unscoped — the auth-off / single-user path.

    Backend failures raise ``PersistenceError`` — the only store error callers may treat as
    best-effort; anything else is a bug and must surface.
    """

    async def upsert(self, *, cost: CourseCost, owner_id: str | None = None) -> None: ...

    async def get(self, *, course_id: str, owner_id: str | None = None) -> CourseCost | None: ...

    async def delete_for_course(self, *, course_id: str, owner_id: str | None = None) -> int: ...
