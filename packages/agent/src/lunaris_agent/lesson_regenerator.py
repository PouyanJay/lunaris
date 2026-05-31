"""The optional per-lesson regeneration capability the delivery API probes for at runtime."""

from typing import Protocol, runtime_checkable

from lunaris_runtime.schema import Course


@runtime_checkable
class LessonRegenerator(Protocol):
    """A pipeline that can re-author a single lesson of an existing course in place.

    Optional capability — the single-shot ``Orchestrator`` implements it; the deep-agent builder
    does not yet — so ``CourseService`` checks for it via ``isinstance`` and 501s otherwise. Note
    ``@runtime_checkable`` verifies only the method *name* exists (not its signature or async-ness);
    that is sufficient given the closed set of known pipelines. Returns ``None`` when the course or
    lesson is unknown.
    """

    async def regenerate_lesson(
        self, course_id: str, lesson_id: str, *, run_id: str
    ) -> Course | None: ...
