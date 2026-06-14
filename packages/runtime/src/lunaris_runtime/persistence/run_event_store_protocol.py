from collections.abc import Sequence
from typing import Protocol

from lunaris_runtime.schema import RunEvent


class IRunEventStore(Protocol):
    """Append-only persistence for a run's streamed build log — the source of timeline *replay*.

    ``CourseService.stream`` records each coarse ``progress`` stage and fine-grained ``agent`` beat
    here as it is forwarded to the live SSE, so a finished (or still-building) run can be
    re-rendered later. ``append`` is batched (a flush may carry many events) and best-effort at the
    call site — a failed log write must never break a build — so implementations may raise; the
    caller swallows. ``seq`` is assigned by the caller (where the two streams interleave into one
    queue), so the store stays a dumb appender and ordering is owned at the one point that sees it.

    Concrete stores: an in-memory fallback (no-key/CI, the test stub) and the Supabase-backed log
    (production). ``list_for_run`` feeds ``GET /api/runs/{run_id}/events``; ``delete_for_course``
    purges the log when the course is deleted.

    ``owner_id`` (Phase 2 per-user scoping) is the authenticated caller's id: ``append`` stamps it
    on each row, ``list_for_run``/``delete_for_course`` constrain to it (another user's transcript
    reads as empty). ``None`` means unscoped — the auth-off / single-user path, today's behavior.

    Backend failures raise ``PersistenceError`` — the only store error callers may
    treat as best-effort; anything else is a bug and must surface.
    """

    async def append(self, *, events: Sequence[RunEvent], owner_id: str | None = None) -> None: ...

    async def latest_seq(self, *, run_id: str, owner_id: str | None = None) -> int | None:
        """The highest ``seq`` a run has logged, or ``None`` if it has none.

        Lets a writer that may run more than once for the same ``run_id`` (a re-claimed video job
        whose first worker was lost mid-render) continue the gap-free sequence PAST the prior
        attempt's events instead of restarting at 0 — the DB's UNIQUE ``(run_id, seq)`` index
        rejects a re-used seq, so a naive restart drops the re-claim's whole transcript.
        """
        ...

    async def list_for_run(self, *, run_id: str, owner_id: str | None = None) -> list[RunEvent]: ...

    async def delete_for_course(self, *, course_id: str, owner_id: str | None = None) -> int: ...
