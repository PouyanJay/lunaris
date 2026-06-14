from collections.abc import Awaitable, Callable
from typing import Protocol

from lunaris_runtime.schema import VideoJob, VideoJobStatus

from lunaris_video.models.rendered_video import RenderedVideo

# A stage reporter the worker passes into ``produce``: the pipeline calls it as it moves through the
# render stages (voicing / rendering / assembling) so the worker can reflect each on the job row and
# the run_events log — the reader's progress bar. Awaited, so a slow write doesn't drop a stage.
StageReporter = Callable[[VideoJobStatus], Awaitable[None]]


class IVideoPipeline(Protocol):
    """Turns one video job into finished artifacts — the seam the real pipeline fills in V1.

    V0 ships ``StubVideoPipeline`` (packaged placeholder media) so the whole job spine is
    provable end-to-end; V1 replaces it with the plan→code→render→QA→assemble LangGraph behind
    this same interface. Implementations raise on failure — the worker settles the job FAILED;
    a pipeline must never return a half-made artifact.

    ``on_stage`` (optional) lets a producer report its progress through the render stages; a
    producer that doesn't care omits it and a caller that doesn't track progress passes ``None``.
    """

    async def produce(
        self, job: VideoJob, *, on_stage: StageReporter | None = None
    ) -> RenderedVideo: ...
