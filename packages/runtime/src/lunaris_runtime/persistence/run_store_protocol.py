from typing import Protocol

from lunaris_runtime.schema import CourseRun, RunStatus


class IRunStore(Protocol):
    """A destination for the course-run history index (the agent-UI sidebar).

    The API's ``CourseService`` records a run's lifecycle through this abstraction (DIP):
    ``start`` at run begin (status ``RUNNING``), ``finish`` at the end (terminal status + the
    knowledge-component / module counts), and ``list_recent`` feeds the sidebar. Concrete stores
    are an in-memory fallback (no-key/CI) and the Supabase-backed index (production). Recording is
    best-effort at the call site — a failed history write must never break a build — so
    implementations may raise; the caller swallows.

    ``owner_id`` (Phase 2 per-user scoping) is the authenticated caller's id: ``start`` stamps it on
    the row, the reads/writes constrain to it (``list_recent`` returns only the caller's runs, and
    finish/get/delete only touch a row the caller owns). ``None`` means unscoped — the auth-off /
    single-user path, byte-for-byte today's behavior.

    Backend failures raise ``PersistenceError`` — the only store error callers may
    treat as best-effort; anything else is a bug and must surface.
    """

    async def start(
        self, *, run_id: str, course_id: str, topic: str, owner_id: str | None = None
    ) -> None: ...

    async def finish(
        self,
        *,
        course_id: str,
        status: RunStatus,
        kc_count: int,
        module_count: int,
        owner_id: str | None = None,
    ) -> None: ...

    async def list_recent(
        self, *, limit: int = 50, owner_id: str | None = None
    ) -> list[CourseRun]: ...

    async def get(self, *, course_id: str, owner_id: str | None = None) -> CourseRun | None: ...

    async def delete(self, *, course_id: str, owner_id: str | None = None) -> bool: ...
