import structlog
from lunaris_runtime.resilience import invoke_with_parse_repair

from lunaris_video.qa.vision_qa_inspector import VisionInvoke
from lunaris_video.schemas import SyncVerdict

_logger = structlog.get_logger(__name__)

_INSPECT_TEMPLATE = """\
You are Gate D of an explainer-video pipeline: the audio-video SYNC gate. You are given ONE frame
extracted at the MIDPOINT of a narrated beat — the instant the narration below is being spoken.

The check is semantic: does the frame show what the words describe AT THIS INSTANT? "the right half
is eliminated" must show a dimmed right half here, not two seconds later; a value the narration
names must already be on screen, not still faded out.

NARRATION SPOKEN AT THIS FRAME
{narration}

VERDICT
Respond with ONLY this JSON object, no prose, no code fences:
{{"matches": true}}  when the frame shows what the narration describes, OR
{{"matches": false, "reason": "what is on screen vs. what the words say"}}  when it does not."""

_REPAIR_TEMPLATE = """

Your previous reply could not be used: {error}
Respond again with ONLY the corrected verdict JSON, exactly as specified above."""


class SyncQaInspector:
    """Concrete ``ISyncQa``: prompts a vision model with one frame + the beat's narration and parses
    a ``SyncVerdict`` with bounded repair turns.

    Provider-agnostic and stub-testable — the composition root adapts a vision-capable chat model
    into the ``VisionInvoke`` seam (the multimodal text + base64 PNG message is built there), just
    as Gate B's inspector does.
    """

    def __init__(self, *, invoke: VisionInvoke) -> None:
        self._invoke = invoke

    async def inspect(self, frame: bytes, *, narration: str, beat_id: str) -> SyncVerdict:
        prompt = _INSPECT_TEMPLATE.format(narration=narration)
        verdict = await invoke_with_parse_repair(
            lambda p: self._invoke(p, [frame]),
            prompt,
            SyncVerdict.model_validate_json,
            repair_instruction=_REPAIR_TEMPLATE,
        )
        _logger.info("sync_qa.inspected", beat_id=beat_id, matches=verdict.matches)
        return verdict
