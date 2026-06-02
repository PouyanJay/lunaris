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
    """

    async def append(self, *, events: Sequence[RunEvent]) -> None: ...

    async def list_for_run(self, *, run_id: str) -> list[RunEvent]: ...

    async def delete_for_course(self, *, course_id: str) -> int: ...
