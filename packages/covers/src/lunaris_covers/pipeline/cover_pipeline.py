from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from lunaris_runtime.schema import CoverJob, CoverJobStatus, CoverLightMode, CoverProvenance

from lunaris_covers.art_direction.cover_art_director import CoverArtDirector
from lunaris_covers.art_direction.house_style import (
    light_native_directive,
    light_retheme_instruction,
)
from lunaris_covers.errors import CoverPipelineError
from lunaris_covers.models.cover_brief import CoverBrief
from lunaris_covers.models.rendered_cover import RenderedCover
from lunaris_covers.protocols.cover_pipeline_protocol import StageReporter
from lunaris_covers.protocols.cover_source_provider_protocol import ICoverSourceProvider
from lunaris_covers.protocols.cover_vision_qa_protocol import ICoverVisionQa
from lunaris_covers.protocols.image_renderer_protocol import IImageRenderer

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _LightVariantInputs:
    """What the light-variant render needs: the passing DARK render to re-theme, the brief (for the
    light QA), the dark art-direction prompt (reused by the native fallback), and the job id (for
    correlation). Bundled so the two light-render helpers take one argument, not four."""

    base: bytes
    brief: CoverBrief
    dark_prompt: str
    job_id: str


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
        inputs = _LightVariantInputs(base=image, brief=brief, dark_prompt=prompt, job_id=job.id)
        image_light, light_mode = await self._render_light_variant(inputs)
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
        self, inputs: _LightVariantInputs
    ) -> tuple[bytes | None, CoverLightMode | None]:
        """The DARK cover's light-theme twin — hybrid, quality-gated, and never a gate on the job.

        Why it's shaped this way: quality is the top priority (requirements), so the light variant
        is always QA'd to the same anti-slop bar as the dark cover — but it is an ENHANCEMENT, so
        any failure degrades to a dark-only cover rather than failing a job whose dark cover already
        passed (the reader then shows the dark image in both themes, like a pre-dual-theme cover).
        It first tries the composition-preserving re-theme (best case: same composition + on-brand);
        a washed re-theme falls through to a native light cover; a bare render (no inspector, local
        dev) keeps the re-theme unjudged, mirroring the dark path's render-once behaviour.

        Every failure mode — a provider error, a QA parse-exhaustion / provider error, or a QA
        rejection — resolves to ``(None, None)`` so it can never propagate out and fail the job."""
        try:
            candidate = await self._renderer.retheme(
                inputs.base, instruction=light_retheme_instruction()
            )
        except CoverPipelineError:
            _logger.warning("cover_pipeline.light_retheme_failed", job_id=inputs.job_id)
            return None, None
        inspector = self._inspector
        if inspector is None:
            return candidate, CoverLightMode.RETHEME
        if await self._passes_light_qa(inspector, candidate, inputs):
            return candidate, CoverLightMode.RETHEME
        return await self._render_native_light(inspector, inputs)

    async def _render_native_light(
        self, inspector: ICoverVisionQa, inputs: _LightVariantInputs
    ) -> tuple[bytes | None, CoverLightMode | None]:
        """Fallback: art-direct a NATIVE light cover when the re-theme failed the light QA bar.

        Renders the passing dark composition prompt under the light directive (same subject, bright
        ground) and QA's it once — bounded to a single native attempt so a stubborn cover can't burn
        the provider budget chasing a light twin the dark cover doesn't need. A render error or a QA
        miss degrades to dark-only."""
        try:
            native = await self._renderer.render(
                f"{inputs.dark_prompt}\n\n{light_native_directive()}"
            )
        except CoverPipelineError:
            _logger.warning("cover_pipeline.light_native_render_failed", job_id=inputs.job_id)
            return None, None
        if await self._passes_light_qa(inspector, native, inputs):
            return native, CoverLightMode.NATIVE
        _logger.info("cover_pipeline.light_variant_dropped", job_id=inputs.job_id)
        return None, None

    async def _passes_light_qa(
        self, inspector: ICoverVisionQa, image: bytes, inputs: _LightVariantInputs
    ) -> bool:
        """Vision-QA a light candidate against the LIGHT rubric, swallowing QA failure as a miss.

        A QA exception (parse-repair exhaustion → ``ValueError``, or a non-rate-limit provider
        error) must NOT fail the job — the light variant is an enhancement — so it counts as "did
        not pass" and the caller degrades to dark-only. ``asyncio.CancelledError`` (a worker
        shutdown /
        owner cancel) is a ``BaseException`` and is deliberately NOT caught, so cancellation still
        aborts the render promptly."""
        try:
            return (await inspector.inspect(image, inputs.brief, light=True)).passed
        except Exception:
            _logger.warning("cover_pipeline.light_qa_failed", job_id=inputs.job_id)
            return False

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
