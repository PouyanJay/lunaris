"""SceneContracts schema tests: the contract file round-trips losslessly and the field rules
from the skill's contract-schema.md are enforced by the schema, not by reviewer discipline."""

from collections.abc import Callable

import pytest
from lunaris_video.schemas import (
    Beat,
    ChapteredSceneContracts,
    GlobalStyle,
    SceneContract,
    SceneContracts,
)
from pydantic import ValidationError


def test_lesson_contract_round_trips_through_json(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    contract = make_lesson_contract()

    # Act
    restored = SceneContracts.model_validate_json(contract.model_dump_json())

    # Assert — lossless: the persisted scene_contracts.json IS the contract.
    assert restored == contract


def test_chaptered_contract_round_trips_through_json(
    make_chaptered_contract: Callable[..., ChapteredSceneContracts],
) -> None:
    # Arrange
    contract = make_chaptered_contract()

    # Act
    restored = ChapteredSceneContracts.model_validate_json(contract.model_dump_json())

    # Assert
    assert restored == contract


def test_contract_json_uses_the_skill_spec_field_names(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    contract = make_lesson_contract()

    # Act — the wire format is the skill's snake_case spec, NOT the web's camelCase.
    payload = contract.model_dump(mode="json")

    # Assert
    assert "global_style" in payload
    assert "visual_archetypes_used" in payload
    assert "duration_s" in payload["scenes"][0]
    assert "min_visual_s" in payload["scenes"][0]["beats"][2]


def test_beat_numeric_fields_survive_serialization(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    contract = make_lesson_contract()

    # Act
    payload = contract.model_dump(mode="json")

    # Assert — the silent beat's visual floor lands in JSON as the number the spec promises.
    assert payload["scenes"][0]["beats"][2]["min_visual_s"] == 1.5
    assert payload["scenes"][0]["duration_s"] == 18


def test_omitted_verifier_gates_default_to_the_spec_three(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange / Act — the factory does not pass verifier_gates.
    contract = make_lesson_contract()

    # Assert — a planner can only ADD gates, never silently drop one by omission.
    assert contract.verifier_gates == [
        "render_success_per_scene",
        "frame_visual_qa",
        "narration_claim_check_vs_sources",
    ]


def test_scene_id_must_match_the_spec_pattern(make_scene: Callable[..., SceneContract]) -> None:
    # Arrange
    scene = make_scene(1, "problem")

    # Act / Assert — "S<N>_<slug>" is what files, logs, QA frames and class names key off.
    with pytest.raises(ValidationError):
        SceneContract(**{**scene.model_dump(), "id": "scene-one"})


def test_spec_conformant_scene_ids_are_accepted(make_scene: Callable[..., SceneContract]) -> None:
    # Arrange
    scene = make_scene(1, "problem")

    # Act — multi-digit scene number, multi-word slug with digits: all inside the spec pattern.
    accepted = SceneContract(**{**scene.model_dump(), "id": "S12_zoom_inset_2"})

    # Assert
    assert accepted.id == "S12_zoom_inset_2"


@pytest.mark.parametrize(
    ("scene_id", "expected_class_name"),
    [
        ("S1_problem", "S1Problem"),
        ("S2_key_insight", "S2KeyInsight"),
        ("S12_zoom_inset_2", "S12ZoomInset2"),
    ],
)
def test_scene_class_name_is_camelcase_of_id(
    make_scene: Callable[..., SceneContract], scene_id: str, expected_class_name: str
) -> None:
    # Arrange
    scene = SceneContract(**{**make_scene(1, "problem").model_dump(), "id": scene_id})

    # Act / Assert — S2_key_insight → S2KeyInsight (the generated Manim class name).
    assert scene.scene_class_name == expected_class_name


def test_sources_must_be_non_empty(make_scene: Callable[..., SceneContract]) -> None:
    # Arrange
    scene = make_scene(1, "problem")

    # Act / Assert — an empty sources list is itself a gate failure (contract-schema field rules).
    with pytest.raises(ValidationError):
        SceneContract(**{**scene.model_dump(), "sources": []})


def test_silent_beat_requires_an_explicit_visual_floor() -> None:
    # Arrange — a silent beat: empty narration, no min_visual_s.
    silent_beat_fields = {"id": "b1", "action": "camera holds", "narration": ""}

    # Act / Assert — with no words to time, the floor is the only duration source.
    with pytest.raises(ValidationError):
        Beat(**silent_beat_fields)


def test_global_style_rejects_non_hex_colors(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    style = make_lesson_contract().global_style

    # Act / Assert — a named color would render, wrongly, on some backends; fail at the contract.
    with pytest.raises(ValidationError):
        GlobalStyle(**{**style.model_dump(), "background": "white"})


def test_duplicate_scene_ids_are_rejected(
    make_lesson_contract: Callable[..., SceneContracts],
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange
    scenes = [make_scene(1, "problem"), make_scene(1, "problem"), make_scene(2, "insight")]

    # Act / Assert — ids key artifacts and Scene classes; a collision corrupts both.
    with pytest.raises(ValidationError):
        make_lesson_contract(scenes=scenes)


def test_unknown_fields_are_rejected(make_scene: Callable[..., SceneContract]) -> None:
    # Arrange
    scene = make_scene(1, "problem")

    # Act / Assert — a planner hallucinating fields must fail loudly, not persist silently.
    with pytest.raises(ValidationError):
        SceneContract(**{**scene.model_dump(), "camera": "zoom"})
