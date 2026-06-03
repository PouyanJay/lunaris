from typing import Protocol

from lunaris_runtime.schema import CourseBrief


class IGoalInterpreter(Protocol):
    """Interprets a raw course request into a typed :class:`CourseBrief`.

    Reads the request as a *goal for a learner at a level* (subject, goal, target level/standard,
    assumed prior knowledge, deliverable shape) rather than a subject to enumerate — the missing
    front of the pipeline that lets backward design run from the right desired result. Swappable
    (live model vs. test stub), like every other subagent collaborator.
    """

    async def interpret(self, request: str) -> CourseBrief: ...
