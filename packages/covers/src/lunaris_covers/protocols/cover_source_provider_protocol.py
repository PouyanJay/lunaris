from typing import Protocol

from lunaris_runtime.schema import CoverJob

from lunaris_covers.models.cover_brief import CoverBrief


class ICoverSourceProvider(Protocol):
    """Loads the art-direction brief for a cover job from wherever the course lives.

    The job carries only ids + the style preset; the topic and concept graph that steer the art
    director come from the ``Course``. The default implementation loads it from the owner-scoped
    course store; the seam keeps the pipeline stub-testable and lets the source vary (a future
    per-course override) without touching the pipeline.
    """

    async def load(self, job: CoverJob) -> CoverBrief: ...
