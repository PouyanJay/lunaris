"""Shared factories for the video package's tests — one honest lesson contract, customizable."""

from collections.abc import Callable

import pytest
from lunaris_video.schemas import (
    Beat,
    Chapter,
    ChapteredSceneContracts,
    GlobalStyle,
    SceneContract,
    SceneContracts,
)
from lunaris_video.style import video_global_style


def _global_style() -> GlobalStyle:
    # The real injected style — the fixtures stay honest to what the planner actually produces.
    return video_global_style()


def _beats() -> list[Beat]:
    return [
        Beat(id="b1", action="title card fades in", narration="Sorting is everywhere."),
        Beat(id="b2", action="array appears cell by cell", narration="Start with eight numbers."),
        Beat(id="b3", action="camera holds on the array", narration="", min_visual_s=1.5),
    ]


def _scene(number: int, slug: str, archetype: str = "process/flow") -> SceneContract:
    return SceneContract(
        id=f"S{number}_{slug}",
        archetype=archetype,
        narration="Sorting is everywhere. Start with eight numbers.",
        objects=["title card", "indexed array of 8 cells"],
        beats=_beats(),
        sources=["framing only - no empirical claims"],
        duration_s=18,
    )


@pytest.fixture
def make_scene() -> Callable[..., SceneContract]:
    return _scene


@pytest.fixture
def make_lesson_contract() -> Callable[..., SceneContracts]:
    def factory(**overrides: object) -> SceneContracts:
        fields: dict[str, object] = {
            "topic": "How merge sort works",
            "audience": "first-year CS students who know arrays",
            "visual_archetypes_used": ["process/flow", "data/array"],
            "asset_strategy": "tier-a procedural",
            "global_style": _global_style(),
            "scenes": [
                _scene(1, "problem"),
                _scene(2, "key_insight", archetype="data/array"),
                _scene(3, "mechanism"),
            ],
        }
        fields.update(overrides)
        return SceneContracts(**fields)  # type: ignore[arg-type]

    return factory


@pytest.fixture
def make_chaptered_contract() -> Callable[..., ChapteredSceneContracts]:
    def factory(**overrides: object) -> ChapteredSceneContracts:
        fields: dict[str, object] = {
            "topic": "What is information theory",
            "audience": "curious newcomers",
            "visual_archetypes_used": ["process/flow"],
            "asset_strategy": "tier-a procedural",
            "global_style": _global_style(),
            "chapters": [
                Chapter(
                    id="ch1",
                    title="The question",
                    scenes=[_scene(1, "hook"), _scene(2, "framing")],
                ),
                Chapter(
                    id="ch2",
                    title="The insight",
                    scenes=[_scene(3, "bits"), _scene(4, "entropy")],
                ),
            ],
        }
        fields.update(overrides)
        return ChapteredSceneContracts(**fields)  # type: ignore[arg-type]

    return factory
