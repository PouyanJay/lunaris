from datetime import UTC, datetime

import structlog
from lunaris_runtime.schema import CoverJob, CoverJobStatus, CoverProvenance

from lunaris_covers.art_direction.cover_art_director import CoverArtDirector
from lunaris_covers.art_direction.house_style import light_retheme_instruction
from lunaris_covers.errors import CoverPipelineError
from lunaris_covers.models.cover_brief import CoverBrief
from lunaris_covers.models.rendered_cover import RenderedCover
from lunaris_covers.protocols.cover_pipeline_protocol import StageReporter
from lunaris_covers.protocols.cover_source_provider_protocol import ICoverSourceProvider
from lunaris_covers.protocols.cover_vision_qa_protocol import ICoverVisionQa
from lunaris_covers.protocols.image_renderer_protocol import IImageRenderer

_logger = structlog.get_logger(__name__)

# How many render → QA rounds a cover gets before the pipeline gives up (the bounded regenerate
# loop). Each round re-art-directs with the prior round's defects. Three balances quality against
# provider cost — an image model that can't produce an on-brand cover in three tries is failing,
# and the reader falls back to the Typographic cover rather than shipping slop.
COVER_MAX_QA_ATTEMPTS = 3


class CoverPipeline:
    """The real cover pipeline (``ICoverPipeline``): course → Claude art director → GPT Image 2 →
    Claude vision-QA, with a bounded regenerate loop.

    Replaces ``StubCoverPipeline`` for the keyed path. It loads the brief (topic + concept graph)
    from the course, has the art director write the house-style prompt, renders it to PNG bytes on
    the tenant's OpenAI key, then — when an ``inspector`` is wired (T5) — has Claude vision-QA the
    render. A rejected cover is regenerated (up to ``max_attempts`` rounds), each round
    re-art-directed with the prior round's defects so it fixes exactly what failed. This loop is the
    anti-slop mechanism that keeps covers a consistent series. ``CoverProvenance`` is stamped at the
    source with the winning ``qa_attempts``. Exhausting the rounds raises ``CoverPipelineError``
    rather than shipping a cover the gate rejected — the worker settles the job FAILED and the
    reader shows the Typographic fallback. Without an inspector (local dev) it renders once.
    """

    def __init__(
        self,
        *,
        source_provider: ICoverSourceProvider,
        art_director: CoverArtDirector,
        renderer: IImageRenderer,
        qa_model: str,
        inspector: ICoverVisionQa | None = None,
        max_attempts: int = COVER_MAX_QA_ATTEMPTS,
    ) -> None:
        self._source_provider = source_provider
        self._art_director = art_director
        self._renderer = renderer
        # The Claude model that vision-QAs the render — recorded in provenance even when no
        # inspector is wired (local dev), documenting the model the anti-slop loop uses when keyed.
        self._qa_model = qa_model
        self._inspector = inspector
        self._max_attempts = max(1, max_attempts)

    async def produce(self, job: CoverJob, *, on_stage: StageReporter) -> RenderedCover:
        brief = await self._source_provider.load(job)
        image, prompt, attempts = await self._render_until_on_brand(brief, on_stage)
        image_light, light_mode = await self._render_light_variant(image, job)
        provenance = CoverProvenance(
            job_id=job.id,
            course_id=job.course_id,
            source="openai",
            model=self._renderer.model,
            art_director_model=self._art_director.model,
            qa_model=self._qa_model,
            style_preset=job.style_preset,
            prompt=prompt,
            qa_attempts=attempts,
            input_hash=job.input_hash,
            generated_at=datetime.now(UTC).isoformat(),
            has_light_variant=image_light is not None,
            light_mode=light_mode,
        )
        _logger.info(
            "cover_pipeline.produced",
            job_id=job.id,
            qa_attempts=attempts,
            image_bytes=len(image),
            light_mode=light_mode,
        )
        return RenderedCover(image=image, image_light=image_light, provenance=provenance)

    async def _render_light_variant(
        self, base: bytes, job: CoverJob
    ) -> tuple[bytes | None, str | None]:
        """The DARK cover's light-theme twin, produced best-effort (dual-theme covers).

        Re-themes the passed dark render into a light palette via the image-edit seam, preserving
        composition (``light_mode="retheme"``). The light variant is an ENHANCEMENT, never a gate:
        the dark cover has already passed QA and is shippable on its own, so a re-theme failure
        degrades to a dark-only cover (``None``) rather than failing the whole job — the reader then
        shows the dark image in both themes, exactly as a pre-dual-theme cover does. The QA gate on
        the light result and the native-light fallback are layered on in T2."""
        try:
            light = await self._renderer.retheme(
                base, instruction=light_retheme_instruction(job.style_preset)
            )
        except CoverPipelineError:
            _logger.warning("cover_pipeline.light_retheme_failed", job_id=job.id)
            return None, None
        return light, "retheme"

    async def _render_until_on_brand(
        self, brief: CoverBrief, on_stage: StageReporter
    ) -> tuple[bytes, str, int]:
        """Art-direct → render → QA, regenerating on a rejected cover up to ``max_attempts`` rounds.

        Returns the winning image, the prompt that produced it, and the round it passed on (the
        provenance ``qa_attempts``). Without an inspector it renders once and returns immediately.
        Exhausting the rounds raises ``CoverPipelineError`` — a rejected cover is never shipped.
        """
        defects: list[str] = []
        prior_prompt: str | None = None
        for attempt in range(1, self._max_attempts + 1):
            await on_stage(CoverJobStatus.ART_DIRECTING)
            prompt = await self._art_director.direct(
                brief, prior_prompt=prior_prompt, defects=defects
            )
            await on_stage(CoverJobStatus.RENDERING)
            image = await self._renderer.render(prompt)
            if self._inspector is None:
                return image, prompt, attempt
            await on_stage(CoverJobStatus.QA)
            verdict = await self._inspector.inspect(image, brief)
            if verdict.passed:
                return image, prompt, attempt
            defects = [defect.issue for defect in verdict.defects]
            prior_prompt = prompt
            _logger.info("cover_pipeline.regenerating", attempt=attempt, defect_count=len(defects))
        raise CoverPipelineError(
            f"cover failed visual QA after {self._max_attempts} attempts: {'; '.join(defects)}",
            user_detail="couldn't produce an on-brand cover after several tries",
        )
