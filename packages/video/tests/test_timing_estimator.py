"""Timing-estimator tests: the WPM estimate reproduces the skill's estimate-mode manifest shape
exactly, so a silent V1 video stays voice-ready — V3 swaps measured TTS timings in later."""

import re
from collections.abc import Callable

from lunaris_video.assembly import estimate_timing
from lunaris_video.assembly import timing_estimator as te
from lunaris_video.schemas import Beat, SceneContract, SceneContracts
from lunaris_video.skill import read_skill_asset
from lunaris_video.style import video_global_style


def test_timing_has_the_skill_manifest_shape(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    contract = make_lesson_contract()

    # Act
    timing = estimate_timing(contract)

    # Assert — one entry per scene; each beat carries the skill's estimate fields.
    assert set(timing) == {scene.id for scene in contract.scenes}
    first = timing[contract.scenes[0].id]
    beat = first["beats"][0]
    assert set(beat) == {"id", "audio_s", "anim_s", "audio", "estimated"}
    assert beat["audio"] is None
    assert beat["estimated"] is True


def test_spoken_beat_duration_follows_the_wpm_model(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — 6 words at 150 wpm = 2.5 words/sec → 2.4s + 0.35 pause = 2.75s.
    scene = make_scene(1, "problem")
    scene = SceneContract(
        **{
            **scene.model_dump(),
            "beats": [{"id": "b1", "action": "x", "narration": "one two three four five six"}],
        }
    )

    # Act
    timing = estimate_timing(SceneContracts(**_with_scenes(scene)))

    # Assert
    beat = timing[scene.id]["beats"][0]
    assert beat["audio_s"] == 2.75
    assert beat["anim_s"] == 2.75


def test_silent_beat_uses_its_visual_floor_not_speech() -> None:
    # Arrange — empty narration, explicit 1.5s floor.
    scene = SceneContract(
        id="S1_hold",
        archetype="process/flow",
        narration="",
        objects=["a held frame"],
        beats=[Beat(id="b1", action="camera holds", narration="", min_visual_s=1.5)],
        sources=["framing only - no empirical claims"],
        duration_s=2,
    )

    # Act
    timing = estimate_timing(SceneContracts(**_with_scenes(scene)))

    # Assert — no speech time, the floor drives the on-screen duration.
    beat = timing[scene.id]["beats"][0]
    assert beat["audio_s"] == 0.0
    assert beat["anim_s"] == 1.5
    assert timing[scene.id]["total_s"] == 1.5


def test_estimate_constants_match_the_pinned_skill_script() -> None:
    # Arrange — the skill's narration.py is the source of truth for the estimate model; this pins
    # our reimplementation to it so a future skill bump that changes WPM/pause/floor turns red
    # instead of silently producing timings the (V3) measured swap won't line up with.
    narration = read_skill_asset("scripts/narration.py")

    # Act
    wpm = float(re.search(r'"--wpm",\s*type=float,\s*default=(\d+(?:\.\d+)?)', narration).group(1))
    pause = float(re.search(r"PAUSE_DEFAULT\s*=\s*(\d+(?:\.\d+)?)", narration).group(1))
    min_beat = float(re.search(r"MIN_BEAT_S\s*=\s*(\d+(?:\.\d+)?)", narration).group(1))

    # Assert
    assert wpm == te._WORDS_PER_MINUTE
    assert pause == te._PAUSE_S
    assert min_beat == te._MIN_BEAT_S


def _with_scenes(scene: SceneContract) -> dict[str, object]:
    return {
        "topic": "t",
        "audience": "a",
        "visual_archetypes_used": ["process/flow"],
        "asset_strategy": "tier-a procedural",
        "global_style": video_global_style(),
        "scenes": [scene],
    }
