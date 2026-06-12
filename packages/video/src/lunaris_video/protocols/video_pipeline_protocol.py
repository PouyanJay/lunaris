from typing import Protocol

from lunaris_runtime.schema import VideoJob

from lunaris_video.models.rendered_video import RenderedVideo


class IVideoPipeline(Protocol):
    """Turns one video job into finished artifacts — the seam the real pipeline fills in V1.

    V0 ships ``StubVideoPipeline`` (packaged placeholder media) so the whole job spine is
    provable end-to-end; V1 replaces it with the plan→code→render→QA→assemble LangGraph behind
    this same interface. Implementations raise on failure — the worker settles the job FAILED;
    a pipeline must never return a half-made artifact.
    """

    async def produce(self, job: VideoJob) -> RenderedVideo: ...
