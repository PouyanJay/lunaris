from typing import Protocol

from lunaris_runtime.schema import CourseBrief

from .profile import LearnerProfile


class ILearnerProfiler(Protocol):
    """Infers what a learner at the brief's level already knows — the ZPD lower bound.

    Maps the interpreted ``CourseBrief`` (target level + subject + assumed prior) to a frontier of
    assumed-known concept descriptors, so gap-scoped extraction can start at the learner's edge
    instead of teaching the whole ladder from zero. Swappable (live model vs. test stub).
    """

    async def profile(self, brief: CourseBrief) -> LearnerProfile: ...
