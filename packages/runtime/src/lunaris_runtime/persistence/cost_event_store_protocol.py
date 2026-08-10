from collections.abc import Sequence
from typing import Protocol

from lunaris_runtime.schema import CostEvent, CostSubjectType


class ICostEventStore(Protocol):
    """Append-only persistence for a subject's build-cost ledger — the drill-through source.

    The cost twin of ``IRunEventStore``: each paid (or metered) call during a build records one
    ``CostEvent`` here. ``append`` is batched (the recorder flushes many at once) and best-effort at
    the call site — a failed cost write must never break a build — so implementations may raise;
    the caller swallows. ``seq`` is assigned by the caller (run-scoped), so the store stays a dumb
    appender. Costs are immutable financial facts: there is no update or delete-by-id, only
    ``delete_for_subject`` when the subject itself is purged.

    ``list_for_subject`` feeds the ledger drill-through (``GET /api/courses/{id}/cost/events``) and
    the rollup recompute; it aggregates every run's events for the subject. ``owner_id`` (per-user
    scoping) is the authenticated caller's id: ``append`` stamps it on each row, and
    ``list_for_subject`` / ``delete_for_subject`` constrain to it (another user's ledger reads as
    empty). ``None`` means unscoped — the auth-off / single-user path.

    Backend failures raise ``PersistenceError`` — the only store error callers may treat as
    best-effort; anything else is a bug and must surface.
    """

    async def append(self, *, events: Sequence[CostEvent], owner_id: str | None = None) -> None: ...

    async def list_for_subject(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> list[CostEvent]: ...

    async def delete_for_subject(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> int: ...
