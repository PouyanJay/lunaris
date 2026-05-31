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
    """

    async def start(self, *, run_id: str, course_id: str, topic: str) -> None: ...

    async def finish(
        self, *, course_id: str, status: RunStatus, kc_count: int, module_count: int
    ) -> None: ...

    async def list_recent(self, *, limit: int = 50) -> list[CourseRun]: ...
