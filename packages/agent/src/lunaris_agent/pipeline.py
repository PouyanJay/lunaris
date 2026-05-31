"""The course-pipeline contract the delivery API depends on.

Both the legacy ``Orchestrator`` and the new ``AgentCourseBuilder`` build a course the same way from
the caller's view — ``run(topic, *, course_id, run_id, progress=None) -> Course`` — so the API's
``CourseService`` drives either through this ``Protocol`` without a concrete type. It is the seam
letting ``LUNARIS_PIPELINE`` pick ``stub`` / ``live`` / ``agent`` at the composition root while the
HTTP layer stays pipeline-agnostic.
"""

from typing import Protocol

from lunaris_runtime.schema import Course

from .progress import IProgressSink


class CoursePipeline(Protocol):
    """Anything that builds a course from a topic and streams progress (orchestrator or agent)."""

    async def run(
        self,
        topic: str,
        *,
        course_id: str,
        run_id: str,
        progress: IProgressSink | None = None,
    ) -> Course: ...
