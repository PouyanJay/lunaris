"""The course-pipeline contract the delivery API depends on.

Both the legacy ``Orchestrator`` and the new ``AgentCourseBuilder`` build a course the same way from
the caller's view — ``run(topic, *, course_id, run_id, progress=None) -> Course`` — so the API's
``CourseService`` drives either through this ``Protocol`` without a concrete type. It is the seam
letting ``LUNARIS_PIPELINE`` pick ``stub`` / ``live`` / ``agent`` at the composition root while the
HTTP layer stays pipeline-agnostic.
"""

from typing import Protocol

from lunaris_runtime.schema import Clarification, Course, DiscoveryDepth

from .progress import IAgentSink, IProgressSink


class CoursePipeline(Protocol):
    """Anything that builds a course from a topic and streams progress (orchestrator or agent).

    ``progress`` carries coarse pipeline stages, ``agent`` the fine-grained transcript feed (both
    default to a no-op sink). ``clarification`` carries the learner's opt-in confirm answers (P7.5);
    the agent pipeline folds them onto the inferred brief, the legacy orchestrator ignores them.
    ``discovery_depth`` pre-authorizes how hard auto-discovery searches (P6.3); the agent pipeline
    reads it, the legacy orchestrator ignores it.
    """

    async def run(
        self,
        topic: str,
        *,
        course_id: str,
        run_id: str,
        progress: IProgressSink | None = None,
        agent: IAgentSink | None = None,
        clarification: Clarification | None = None,
        discovery_depth: DiscoveryDepth = DiscoveryDepth.STANDARD,
    ) -> Course: ...
