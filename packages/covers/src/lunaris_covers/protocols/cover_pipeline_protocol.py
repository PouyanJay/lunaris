from collections.abc import Awaitable, Callable
from typing import Protocol

from lunaris_runtime.schema import CoverJob, CoverJobStatus

from lunaris_covers.models.rendered_cover import RenderedCover

# The pipeline calls this per in-flight stage so the worker can reflect progress on the job row
# (rendering / qa) — the reader's cover slot polls that status. Best-effort; never fails the render.
StageReporter = Callable[[CoverJobStatus], Awaitable[None]]


class ICoverPipeline(Protocol):
    """Produces a course cover image from a cover job.

    The real pipeline (Phase 2) is the anti-slop loop: Claude writes a house-style prompt from the
    course topic + concept graph → GPT Image 2 renders → Claude vision-QA inspects → bounded
    regenerate. The stub pipeline (T0) returns a trivial placeholder so the walking skeleton proves
    the queue → worker → storage → API → web path before any provider calls exist. Both honour the
    same contract: return a ``RenderedCover`` (image bytes + structural provenance), reporting
    render stages via ``on_stage``. A failure raises ``CoverPipelineError``.
    """

    async def produce(self, job: CoverJob, *, on_stage: StageReporter) -> RenderedCover: ...
