from collections.abc import Awaitable, Callable

import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair

from lunaris_video.schemas import QaVerdict, SceneContract
from lunaris_video.skill import read_skill_asset

_logger = structlog.get_logger(__name__)

# The vision seam: judge a text prompt against a batch of frame images, return raw text. The
# composition root adapts a vision-capable chat model into this (the multimodal message — text +
# base64 PNG blocks — is built there); the inspector stays provider-agnostic and stub-testable.
VisionInvoke = Callable[[str, list[bytes]], Awaitable[str]]

_INSPECT_TEMPLATE = """\
You are Gate B of an explainer-video pipeline: the visual-QA gate. Logically-correct Manim code
routinely renders visually-broken output that no stack trace catches, so you LOOK at the frames.

You are given {frame_count} frames sampled at 30%, 60% and 90% of this scene's duration — defects
appear and disappear as the scene animates, so judge across ALL frames, not one.

SCENE INTENT
- id: {scene_id}
- what must be on screen: {objects}
- narration (what the visuals should be showing as it is spoken): {narration}

CHECK EVERY ITEM (verbatim from the pinned skill's QA gate)
{checklist}

VERDICT
Respond with ONLY this JSON object, no prose, no code fences:
{{"passed": true}}  when every item is clean, OR
{{"passed": false, "defects": [{{"issue": "what is wrong, citing the checklist item",
"fix_hint": "the smallest Manim edit that fixes it"}}]}}  when any item fails.
A passing verdict must have NO defects; a failing verdict must name at least one."""

_REPAIR_TEMPLATE = """

Your previous reply could not be used: {error}
Respond again with ONLY the corrected verdict JSON, exactly as specified above."""

# The checklist items (the pinned qa-gates.md Gate-B list) — sliced from the vendored reference so
# the judge sees the SAME bullets a human reviewer would, and an upstream skill bump flows through.
_CHECKLIST_HEADER = "Then actually LOOK at every frame with vision and check:"


class VisionQaInspector:
    """Concrete ``IVisionQa``: prompts a vision model with the QA checklist and the scene's frames,
    parses a structured ``QaVerdict`` with bounded repair turns.

    The checklist is sliced from the pinned ``qa-gates.md`` so the model audits the exact bullets
    the skill validated — never a paraphrase that could drop a defect class.
    """

    def __init__(self, *, invoke: VisionInvoke) -> None:
        self._invoke = invoke
        self._checklist = _extract_checklist()

    async def inspect(self, frames: list[bytes], scene: SceneContract) -> QaVerdict:
        prompt = _INSPECT_TEMPLATE.format(
            frame_count=len(frames),
            scene_id=scene.id,
            objects=", ".join(scene.objects),
            narration=scene.narration,
            checklist=self._checklist,
        )
        verdict = await invoke_with_parse_repair(
            lambda p: self._invoke(p, frames),
            prompt,
            QaVerdict.model_validate_json,
            repair_instruction=_REPAIR_TEMPLATE,
        )
        _logger.info(
            "vision_qa.inspected",
            scene_id=scene.id,
            passed=verdict.passed,
            defect_count=len(verdict.defects),
        )
        return verdict


_CHECKLIST_END = "\nFix →"


def _extract_checklist() -> str:
    gates = read_skill_asset("references/qa-gates.md")
    header_at = gates.find(_CHECKLIST_HEADER)
    end_at = gates.find(_CHECKLIST_END, header_at)
    if header_at < 0 or end_at < 0:
        # The pin is fingerprint-tested, so this should be impossible — but a clear message beats
        # a bare "substring not found" if an upstream skill bump ever moves these markers.
        raise RuntimeError("pinned qa-gates.md is missing the Gate B checklist markers")
    return gates[header_at + len(_CHECKLIST_HEADER) : end_at].strip()
