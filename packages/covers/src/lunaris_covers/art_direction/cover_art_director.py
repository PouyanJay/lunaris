from collections.abc import Awaitable, Callable, Sequence

import structlog

from lunaris_covers.art_direction.house_style import house_style
from lunaris_covers.models.cover_brief import CoverBrief

_logger = structlog.get_logger(__name__)

# The text seam: Claude reasons about the brief and returns the image-generation prompt as plain
# text. The composition root adapts a chat model into this (BYOK-scoped); the director stays
# provider-agnostic and stub-testable. Mirrors ``lunaris_video``'s ``TextInvoke``.
TextInvoke = Callable[[str], Awaitable[str]]

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
render directly. Describe the ONE focal subject, the composition and negative space, and the \
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


class CoverArtDirector:
    """Turns a ``CoverBrief`` into the house-style image-generation prompt (the anti-slop brief).

    Claude reads the course topic + concept graph and the preset's house style and writes the exact
    prompt GPT Image 2 renders. Keeping the discipline in the prompt AND the matching QA rubric (T5)
    is what makes covers a consistent series instead of one-off generations. On a regenerate round,
    ``prior_prompt`` + the QA ``defects`` are appended so the revision fixes exactly what failed.
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
        prompt = _DIRECTION_TEMPLATE.format(
            topic=brief.topic,
            concepts=", ".join(brief.concept_labels) or brief.topic,
            audience=brief.audience,
            style=house_style(brief.style_preset).as_prompt_block(),
        )
        if prior_prompt is not None and defects:
            prompt += _REVISION_TEMPLATE.format(
                prior_prompt=prior_prompt, defects="; ".join(defects)
            )
        image_prompt = (await self._invoke(prompt)).strip()
        _logger.info(
            "cover_art_director.directed",
            style=brief.style_preset.value,
            concept_count=len(brief.concept_labels),
            prompt_chars=len(image_prompt),
            revision=bool(defects),
        )
        return image_prompt
