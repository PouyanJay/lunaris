"""VisionQaInspector tests (stubbed vision model): the checklist prompt carries the skill's QA
items and the scene's intent, the frames reach the model, and a malformed verdict gets bounded
repair turns before failing."""

import json
from collections.abc import Callable

import pytest
from _stubs import StubVisionModel
from lunaris_runtime.resilience import DEFAULT_PARSE_REPAIR_ATTEMPTS
from lunaris_video.qa import VisionQaInspector
from lunaris_video.schemas import SceneContract

_FRAMES = [b"\x89PNG-30", b"\x89PNG-60", b"\x89PNG-90"]


async def test_clean_frames_yield_a_passing_verdict(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange
    stub = StubVisionModel([json.dumps({"passed": True, "defects": []})])
    inspector = VisionQaInspector(invoke=stub)

    # Act
    verdict = await inspector.inspect(_FRAMES, make_scene(1, "problem"))

    # Assert
    assert verdict.passed
    assert stub.frame_batches[0] == _FRAMES  # every extracted frame reached the model


async def test_defective_frames_yield_named_defects(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange
    payload = {
        "passed": False,
        "defects": [{"issue": "blades detached from nacelle", "fix_hint": "pivot anchor"}],
    }
    stub = StubVisionModel([json.dumps(payload)])
    inspector = VisionQaInspector(invoke=stub)

    # Act
    verdict = await inspector.inspect(_FRAMES, make_scene(1, "problem"))

    # Assert
    assert not verdict.passed
    assert verdict.defects[0].issue == "blades detached from nacelle"


async def test_prompt_carries_the_checklist_and_scene_intent(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange
    stub = StubVisionModel([json.dumps({"passed": True, "defects": []})])
    inspector = VisionQaInspector(invoke=stub)
    scene = make_scene(1, "problem")

    # Act
    await inspector.inspect(_FRAMES, scene)

    # Assert — the pinned QA checklist items and the scene's declared objects ground the judge.
    prompt = stub.prompts[0]
    assert "pivot" in prompt.lower()
    assert "clipped" in prompt.lower()
    assert scene.objects[0] in prompt


async def test_malformed_verdict_is_repaired_then_parsed(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — first reply is not valid JSON, second is clean.
    stub = StubVisionModel(
        ["the frames look fine to me", json.dumps({"passed": True, "defects": []})]
    )
    inspector = VisionQaInspector(invoke=stub)

    # Act
    verdict = await inspector.inspect(_FRAMES, make_scene(1, "problem"))

    # Assert
    assert verdict.passed
    assert len(stub.prompts) == 2


async def test_a_contradictory_verdict_is_rejected_and_repaired(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — "passed with defects" violates the schema invariant; it must trigger a repair.
    contradiction = json.dumps(
        {"passed": True, "defects": [{"issue": "overlap", "fix_hint": "space"}]}
    )
    clean = json.dumps({"passed": True, "defects": []})
    stub = StubVisionModel([contradiction, clean])
    inspector = VisionQaInspector(invoke=stub)

    # Act
    verdict = await inspector.inspect(_FRAMES, make_scene(1, "problem"))

    # Assert
    assert verdict.passed
    assert len(stub.prompts) == 2


async def test_persistently_unparseable_verdict_raises(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange
    stub = StubVisionModel(["nope"])
    inspector = VisionQaInspector(invoke=stub)

    # Act / Assert — bounded: it gives up after the repair budget, not forever.
    with pytest.raises(ValueError):
        await inspector.inspect(_FRAMES, make_scene(1, "problem"))
    assert len(stub.prompts) == DEFAULT_PARSE_REPAIR_ATTEMPTS


async def test_prompt_carries_all_nine_pinned_checklist_bullets(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange
    stub = StubVisionModel([json.dumps({"passed": True, "defects": []})])
    inspector = VisionQaInspector(invoke=stub)

    # Act
    await inspector.inspect(_FRAMES, make_scene(1, "problem"))

    # Assert — every Gate-B defect class the skill validated reaches the judge, none dropped.
    assert stub.prompts[0].count("- [ ]") == 9


def test_missing_checklist_markers_raise_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — a pinned file whose Gate-B markers an upstream bump moved away.
    monkeypatch.setattr(
        "lunaris_video.qa.vision_qa_inspector.read_skill_asset",
        lambda _name: "## Some other gate\nno checklist here",
    )

    # Act / Assert — fail at construction with a message that names the cause, not "substring
    # not found".
    with pytest.raises(RuntimeError, match="Gate B checklist markers"):
        VisionQaInspector(invoke=StubVisionModel([]))
