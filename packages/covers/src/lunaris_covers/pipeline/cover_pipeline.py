from datetime import UTC, datetime

import structlog
from lunaris_runtime.schema import CoverJob, CoverJobStatus, CoverProvenance

from lunaris_covers.art_direction.cover_art_director import CoverArtDirector
from lunaris_covers.models.rendered_cover import RenderedCover
from lunaris_covers.protocols.cover_pipeline_protocol import StageReporter
from lunaris_covers.protocols.cover_source_provider_protocol import ICoverSourceProvider
from lunaris_covers.protocols.image_renderer_protocol import IImageRenderer

_logger = structlog.get_logger(__name__)


class CoverPipeline:
    """The real cover pipeline (``ICoverPipeline``): course → Claude art director → GPT Image 2.

    Replaces ``StubCoverPipeline`` for the keyed path. It loads the brief (topic + concept graph)
    from the course, has the art director write the house-style prompt, then renders it to PNG bytes
    on the tenant's OpenAI key, and stamps ``CoverProvenance`` at the source (T4). The Claude
    vision-QA gate + a bounded regenerate loop wrap this render in T5; today it is a single pass, so
    ``qa_attempts`` is 1. Stages are reported (``ART_DIRECTING`` → ``RENDERING``) so the reader's
    cover slot reflects progress. A failure at any stage raises ``CoverPipelineError`` (the source
    provider / renderer already do), which the worker turns into a settled-FAILED job.
    """

    def __init__(
        self,
        *,
        source_provider: ICoverSourceProvider,
        art_director: CoverArtDirector,
        renderer: IImageRenderer,
        qa_model: str,
    ) -> None:
        self._source_provider = source_provider
        self._art_director = art_director
        self._renderer = renderer
        # The Claude model that vision-QAs the render. Recorded in provenance from T4 (the gate that
        # uses it lands in T5) so the anti-slop loop's models are documented the moment covers ship.
        self._qa_model = qa_model

    async def produce(self, job: CoverJob, *, on_stage: StageReporter) -> RenderedCover:
        brief = await self._source_provider.load(job)
        await on_stage(CoverJobStatus.ART_DIRECTING)
        prompt = await self._art_director.direct(brief)
        await on_stage(CoverJobStatus.RENDERING)
        image = await self._renderer.render(prompt)
        provenance = CoverProvenance(
            job_id=job.id,
            course_id=job.course_id,
            source="openai",
            model=self._renderer.model,
            art_director_model=self._art_director.model,
            qa_model=self._qa_model,
            style_preset=job.style_preset,
            prompt=prompt,
            qa_attempts=1,
            input_hash=job.input_hash,
            generated_at=datetime.now(UTC).isoformat(),
        )
        _logger.info("cover_pipeline.produced", job_id=job.id, image_bytes=len(image))
        return RenderedCover(image=image, provenance=provenance)
