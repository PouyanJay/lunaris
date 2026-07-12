from collections.abc import Awaitable, Callable

import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair

from lunaris_covers.art_direction.house_style import (
    EDITORIAL_PRESETS,
    house_style,
    light_style_block,
)
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
{text_check}
IT MUST OBEY THE HOUSE STYLE
{style}

CHECK the rendered image against every constraint above. Reject "AI slop": a busy or cluttered \
composition, a palette, finish or subject that violates the house style above, or any lettering \
that breaks the text rules stated above for this cover.

VERDICT
Respond with ONLY this JSON object, no prose, no code fences:
{{"passed": true}}  when the cover obeys every constraint, OR
{{"passed": false, "defects": [{{"issue": "what is wrong, citing the constraint it breaks"}}]}}  \
when any constraint fails.
A passing verdict must have NO defects; a failing verdict must name at least one."""

# The typography check (general-cover-typography). A GENERAL cover typesets its own title, so the
# gate's job flips: instead of rejecting ANY text it must verify the text is RIGHT. A misspelled or
# garbled title is worse than no cover — it ships a broken artifact — so this is a hard reject that
# sends the round back to the art director.
_TEXT_CHECK_TEMPLATE = """
THIS COVER CARRIES TYPOGRAPHY — VERIFY IT CHARACTER BY CHARACTER
The rendered title must read EXACTLY (ignoring line breaks and letter case): "{title}"
REJECT the cover if ANY of these is true:
- a word in the title is misspelled, garbled, invented, or has malformed/duplicated letterforms
- the title text differs from the expected title above
- any rendered text is illegible, cut off, overlapping the artwork, or duplicated
- there is lorem-ipsum or nonsense lettering anywhere
Legible, correctly-spelled supporting text (the eyebrow, subtitle, badge captions, small callout \
labels) is EXPECTED and must NOT be treated as a defect.
"""

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

    async def inspect(
        self, image: bytes, brief: CoverBrief, *, light: bool = False
    ) -> CoverQaVerdict:
        # A light-theme variant is judged against the light rubric (bright ground); the dark
        # rubric's near-black-ground constraint would reject any correct light cover. Same
        # brief/topic either way — only the house-style block the image must obey differs.
        style = (
            light_style_block(brief.style_preset)
            if light
            else house_style(brief.style_preset).as_prompt_block()
        )
        # A cover that typesets its own title (GENERAL) inverts the gate's text rule: instead of
        # rejecting ANY lettering it must verify the title is spelled EXACTLY right — a garbled
        # title ships a broken artifact. The editorial presets stay wordless, so they get no block
        # and their rubric's "NO text" constraint still rejects any lettering at all.
        text_check = (
            ""
            if brief.style_preset in EDITORIAL_PRESETS
            else _TEXT_CHECK_TEMPLATE.format(title=brief.topic)
        )
        prompt = _INSPECT_TEMPLATE.format(
            topic=brief.topic,
            concepts=", ".join(brief.concept_labels) or brief.topic,
            style=style,
            text_check=text_check,
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
            variant="light" if light else "dark",
            passed=verdict.passed,
            defect_count=len(verdict.defects),
        )
        return verdict
