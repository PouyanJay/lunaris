from collections.abc import Awaitable, Callable, Sequence

import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair

from lunaris_covers.art_direction.house_style import (
    EDITORIAL_PRESETS,
    build_general_prompt,
    house_style,
)
from lunaris_covers.errors import CoverPipelineError
from lunaris_covers.models.cover_brief import CoverBrief
from lunaris_covers.schemas.general_cover_fields import GeneralCoverFields

_logger = structlog.get_logger(__name__)

# The text seam: Claude reasons about the brief and returns text. The composition root adapts a
# chat model into this (BYOK-scoped); the director stays provider-agnostic and stub-testable.
# Mirrors ``lunaris_video``'s ``TextInvoke``.
TextInvoke = Callable[[str], Awaitable[str]]

# ---- The EDITORIAL path (nocturne/blueprint/aurora): Claude writes the whole prompt as prose. ----

_DIRECTION_TEMPLATE = """\
You are the art director for Lunaris, an editorial course platform. Design ONE cover image for a \
course so that every Lunaris cover reads as a consistent, tasteful series — never generic "AI slop".

COURSE
- topic: {topic}
- key concepts: {concepts}
- audience: {audience}

HOUSE STYLE
{style}

YOUR TASK
Write a single vivid image-generation prompt (2-4 sentences) that a text-to-image model will \
render directly. Describe the focal subject matter, the composition and negative space, and the \
palette, obeying every constraint above. Do NOT ask the model to add any text or labels. Respond \
with ONLY the image prompt itself — no preamble, no quotes, no commentary."""

# Appended when a prior render was rejected by the vision-QA gate (the regenerate round): the prior
# prompt plus the named defects, so Claude revises the brief to fix exactly what failed rather than
# re-rolling blindly.
_REVISION_TEMPLATE = """\


THE PREVIOUS ATTEMPT WAS REJECTED
- prior prompt: {prior_prompt}
- defects the visual-QA gate found: {defects}
Revise the brief to fix EVERY defect above while still obeying the house style. Respond with ONLY \
the corrected image prompt."""

# ---- The GENERAL path (general-preset template fidelity): Claude fills ONLY the template's ----
# descriptive fields; the full structured prompt is assembled deterministically and sent to the
# image model verbatim. This is the operator's own workflow — compressing the spec into prose is
# exactly what made general covers diverge from the reference look.

_GENERAL_FIELDS_TEMPLATE = """\
You are the art director for Lunaris, a premium course platform. A structured cover-prompt \
template will be assembled around your answers and sent to a text-to-image model — you write ONLY \
the descriptive fields below, tailored to this course.

COURSE
- topic: {topic}
- key concepts: {concepts}
- audience: {audience}

HOUSE STYLE (the template enforces this; your fields must fit inside it)
{style}

YOUR TASK
Write LITERAL, textbook-accurate scene descriptions with sharp, concrete nouns — depict the actual \
subject itself (real organs, devices, systems, structures), the way a medical or technical \
illustrator would. Never use "suggesting", "implying", "evoking" or "hinting" language, and never \
dreamy words (drifting, motes, wisps, subtle glow) — every element is a crisp, defined object. \
Supporting elements must be SEPARATE stand-alone objects arranged around the hero (a magnified \
circular inset revealing internal structure, discrete floating components, individual cells/parts) \
— never features fused onto the hero.

Respond with ONLY this JSON object, no prose, no code fences:
{{"subtitle": "a short supporting subtitle for the course",
  "subject": "one clear sentence naming the literal subject to depict",
  "primary_visual": "the hero — a recognizable, literal depiction, crisp physical detail",
  "supporting_visuals": "2-4 SEPARATE stand-alone elements (inset magnification, floating parts)",
  "process_visualization": "the mechanism as a flow between the separate elements, no text"}}"""

_GENERAL_REVISION_TEMPLATE = """\


THE PREVIOUS ATTEMPT WAS REJECTED
- defects the visual-QA gate found: {defects}
Write NEW field values that fix EVERY defect above while still fitting the house style. Respond \
with ONLY the corrected JSON object."""

_GENERAL_REPAIR_TEMPLATE = """

Your previous reply could not be used: {error}
Respond again with ONLY the JSON object, exactly as specified above."""


class CoverArtDirector:
    """Turns a ``CoverBrief`` into the image-generation prompt GPT Image 2 renders.

    Two regimes, split by preset family. EDITORIAL (nocturne/blueprint/aurora): Claude writes the
    whole prompt as short prose against the house style — the original anti-slop brief. GENERAL:
    Claude fills only the descriptive fields of the operator's structured template
    (``GeneralCoverFields``, parsed with bounded repair turns) and the full template is assembled
    deterministically — so the image model always sees the complete spec, never a paraphrase. On a
    regenerate round the QA ``defects`` are folded in so the revision fixes exactly what failed.
    ``model`` is surfaced so the pipeline can record it in provenance (the art-director model).
    """

    def __init__(self, *, invoke: TextInvoke, model: str) -> None:
        self._invoke = invoke
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def direct(
        self,
        brief: CoverBrief,
        *,
        prior_prompt: str | None = None,
        defects: Sequence[str] = (),
    ) -> str:
        if brief.style_preset in EDITORIAL_PRESETS:
            image_prompt = await self._direct_editorial(brief, prior_prompt, defects)
        else:
            image_prompt = await self._direct_general(brief, defects)
        _logger.info(
            "cover_art_director.directed",
            style=brief.style_preset.value,
            concept_count=len(brief.concept_labels),
            prompt_chars=len(image_prompt),
            revision=bool(defects),
        )
        return image_prompt

    async def _direct_editorial(
        self, brief: CoverBrief, prior_prompt: str | None, defects: Sequence[str]
    ) -> str:
        prompt = _DIRECTION_TEMPLATE.format(
            topic=brief.topic,
            concepts=self._concepts(brief),
            audience=brief.audience,
            style=house_style(brief.style_preset).as_prompt_block(),
        )
        if prior_prompt is not None and defects:
            prompt += _REVISION_TEMPLATE.format(
                prior_prompt=prior_prompt, defects="; ".join(defects)
            )
        return (await self._invoke(prompt)).strip()

    async def _direct_general(self, brief: CoverBrief, defects: Sequence[str]) -> str:
        """Claude fills the fields; the operator's template does the rest, byte-stable.

        The revision round deliberately omits the prior FULL prompt (it is dominated by the fixed
        template Claude cannot change) — the defects alone steer the new field values."""
        prompt = _GENERAL_FIELDS_TEMPLATE.format(
            topic=brief.topic,
            concepts=self._concepts(brief),
            audience=brief.audience,
            style=house_style(brief.style_preset).as_prompt_block(),
        )
        if defects:
            prompt += _GENERAL_REVISION_TEMPLATE.format(defects="; ".join(defects))
        try:
            fields = await invoke_with_parse_repair(
                self._invoke,
                prompt,
                GeneralCoverFields.model_validate_json,
                repair_instruction=_GENERAL_REPAIR_TEMPLATE,
            )
        except ValueError as exc:
            # Repair turns exhausted (ValidationError is a ValueError). Wrap so the worker settles
            # the job with an actionable owner-safe reason instead of a raw exception class name.
            raise CoverPipelineError(
                "general cover fields did not parse after repair turns",
                user_detail="couldn't write the cover's descriptive fields",
            ) from exc
        return build_general_prompt(
            title=brief.topic, key_concepts=self._concepts(brief), fields=fields
        )

    @staticmethod
    def _concepts(brief: CoverBrief) -> str:
        return ", ".join(brief.concept_labels) or brief.topic
