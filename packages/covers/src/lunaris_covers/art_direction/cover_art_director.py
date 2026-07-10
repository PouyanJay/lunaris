from collections.abc import Awaitable, Callable

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


class CoverArtDirector:
    """Turns a ``CoverBrief`` into the house-style image-generation prompt (the anti-slop brief).

    Claude reads the course topic + concept graph and the preset's house style and writes the exact
    prompt GPT Image 2 renders. Keeping the discipline in the prompt (and, in T5, the matching QA
    rubric) is what makes covers a consistent series instead of one-off generations. ``model`` is
    surfaced so the pipeline can record it in provenance (the art-director model).
    """

    def __init__(self, *, invoke: TextInvoke, model: str) -> None:
        self._invoke = invoke
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def direct(self, brief: CoverBrief) -> str:
        prompt = _DIRECTION_TEMPLATE.format(
            topic=brief.topic,
            concepts=", ".join(brief.concept_labels) or brief.topic,
            audience=brief.audience,
            style=house_style(brief.style_preset).as_prompt_block(),
        )
        image_prompt = (await self._invoke(prompt)).strip()
        _logger.info(
            "cover_art_director.directed",
            style=brief.style_preset.value,
            concept_count=len(brief.concept_labels),
            prompt_chars=len(image_prompt),
        )
        return image_prompt
