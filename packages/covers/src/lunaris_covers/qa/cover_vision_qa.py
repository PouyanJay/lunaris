from collections.abc import Awaitable, Callable

import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair

from lunaris_covers.art_direction.house_style import house_style
from lunaris_covers.models.cover_brief import CoverBrief
from lunaris_covers.schemas.cover_qa_verdict import CoverQaVerdict

_logger = structlog.get_logger(__name__)

# The vision seam: judge a text prompt against the rendered cover image, return raw text. The
# composition root adapts a vision-capable chat model into this (the multimodal message is built
# there); the inspector stays provider-agnostic and stub-testable. Mirrors ``lunaris_video``.
VisionInvoke = Callable[[str, list[bytes]], Awaitable[str]]

_INSPECT_TEMPLATE = """\
You are the visual-QA gate of Lunaris's course-cover pipeline: the anti-slop check. An image model \
routinely produces off-brand, cluttered, or text-garbled covers that no automated check catches, \
so you LOOK at the cover.

THE COVER SHOULD EVOKE
- topic: {topic}
- key concepts: {concepts}

IT MUST OBEY THE HOUSE STYLE
{style}

CHECK the rendered image against every constraint above. Reject "AI slop": any readable/garbled \
text or letterforms, a busy or cluttered composition, an off-brand palette, a photoreal-stock or \
generic-3D finish, or a subject that ignores the topic.

VERDICT
Respond with ONLY this JSON object, no prose, no code fences:
{{"passed": true}}  when the cover obeys every constraint, OR
{{"passed": false, "defects": [{{"issue": "what is wrong, citing the constraint it breaks"}}]}}  \
when any constraint fails.
A passing verdict must have NO defects; a failing verdict must name at least one."""

_REPAIR_TEMPLATE = """

Your previous reply could not be used: {error}
Respond again with ONLY the corrected verdict JSON, exactly as specified above."""


class CoverVisionQa:
    """Concrete ``ICoverVisionQa``: prompts a vision model with the house-style rubric and the
    rendered cover, parsing a structured ``CoverQaVerdict`` with bounded parse-repair turns.

    The rubric is built from the SAME ``house_style`` the art director prompts with, so the judge
    audits the exact constraints the prompt asked for — the pipeline can never drift into two
    definitions of "on brand". ``model`` is surfaced for provenance (the QA model).
    """

    def __init__(self, *, invoke: VisionInvoke, model: str) -> None:
        self._invoke = invoke
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def inspect(self, image: bytes, brief: CoverBrief) -> CoverQaVerdict:
        prompt = _INSPECT_TEMPLATE.format(
            topic=brief.topic,
            concepts=", ".join(brief.concept_labels) or brief.topic,
            style=house_style(brief.style_preset).as_prompt_block(),
        )
        verdict = await invoke_with_parse_repair(
            lambda p: self._invoke(p, [image]),
            prompt,
            CoverQaVerdict.model_validate_json,
            repair_instruction=_REPAIR_TEMPLATE,
        )
        _logger.info(
            "cover_vision_qa.inspected",
            style=brief.style_preset.value,
            passed=verdict.passed,
            defect_count=len(verdict.defects),
        )
        return verdict
