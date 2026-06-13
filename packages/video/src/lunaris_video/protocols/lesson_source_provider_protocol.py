from typing import Protocol

from lunaris_runtime.schema import VideoJob

from lunaris_video.models import LessonSource


class ILessonSourceProvider(Protocol):
    """Resolves a job into the lesson content the pipeline plans from.

    The seam that keeps the pipeline decoupled from where lessons live: V1 loads from the course
    store; V2 enriches with the grounding packet (verified claims) behind the same interface.
    """

    async def load(self, job: VideoJob) -> LessonSource: ...
