from lunaris_runtime.schema import CourseBrief

from .profile import LearnerProfile


class StubLearnerProfiler:
    """Returns a preconfigured profile. Lets the pipeline be tested without a model."""

    def __init__(self, profile: LearnerProfile) -> None:
        self._profile = profile

    async def profile(self, brief: CourseBrief) -> LearnerProfile:
        return self._profile
