"""Gate D vision-inspector tests (V3-T4): one frame + a beat's narration → a parsed SyncVerdict,
with the beat's words in the prompt and a bounded repair turn around a malformed completion."""

import json

import pytest
from _stubs import StubVisionModel
from lunaris_runtime.resilience import DEFAULT_PARSE_REPAIR_ATTEMPTS
from lunaris_video.qa import SyncQaInspector

_FRAME = b"\x89PNG-frame-bytes"


async def test_a_matching_frame_parses_to_a_pass() -> None:
    # Arrange — the model affirms the frame shows what the words describe.
    stub = StubVisionModel([json.dumps({"matches": True})])

    # Act
    verdict = await SyncQaInspector(invoke=stub).inspect(
        _FRAME, narration="The right half is eliminated.", beat_id="b2"
    )

    # Assert — the verdict, and the spoken words + the one frame reached the vision seam.
    assert verdict.matches is True
    assert "The right half is eliminated." in stub.prompts[0]
    assert stub.frame_batches[0] == [_FRAME]


async def test_a_mismatch_carries_the_reason() -> None:
    # Arrange — the frame lags the narration; the model says why.
    stub = StubVisionModel([json.dumps({"matches": False, "reason": "both halves still lit"})])

    # Act
    verdict = await SyncQaInspector(invoke=stub).inspect(
        _FRAME, narration="The right half is eliminated.", beat_id="b2"
    )

    # Assert
    assert verdict.matches is False
    assert verdict.reason == "both halves still lit"


async def test_a_malformed_verdict_triggers_a_repair_turn() -> None:
    # Arrange — first reply is a bare mismatch with no reason (invalid); the repair turn fixes it.
    bad = json.dumps({"matches": False})
    good = json.dumps({"matches": False, "reason": "the value has not faded in yet"})
    stub = StubVisionModel([bad, good])

    # Act
    verdict = await SyncQaInspector(invoke=stub).inspect(
        _FRAME, narration="The hash appears.", beat_id="b1"
    )

    # Assert — a second turn was needed; the corrected verdict carries its reason.
    assert len(stub.prompts) == 2
    assert verdict.matches is False
    assert verdict.reason == "the value has not faded in yet"


async def test_a_persistently_invalid_verdict_exhausts_the_repair_budget() -> None:
    # Arrange — every reply is a reason-less mismatch (invalid); no turn ever parses.
    stub = StubVisionModel([json.dumps({"matches": False})])

    # Act / Assert — the inspector propagates the parse failure after the bounded turns (Gate D
    # never silently ships an unparseable verdict; the worker settles the job FAILED).
    with pytest.raises(ValueError):
        await SyncQaInspector(invoke=stub).inspect(_FRAME, narration="x", beat_id="b1")
    assert len(stub.prompts) == DEFAULT_PARSE_REPAIR_ATTEMPTS
