"""WebVTT caption tests (V3-T3): captions are free from beat narration + the measured timeline.

A cue per SPOKEN beat, timed on the GLOBAL (concatenated) timeline by cumulative anim_s; silent
beats advance the clock but emit no cue. Built from the contract (the words) and the manifest (the
timing), so a narrated video ships WCAG-2.2-AA captions that line up with what is said.
"""

import re
from collections.abc import Callable

from lunaris_video.assembly import SCENE_CLOSE_FADE_S, build_webvtt, estimate_timing
from lunaris_video.schemas import (
    Beat,
    BeatTiming,
    SceneContract,
    SceneContracts,
    SceneTiming,
    TimingManifest,
    VoiceSpec,
)
from lunaris_video.style import video_global_style
from lunaris_video.voice import StubSpeechSynthesizer

_VOICE = VoiceSpec(provider="elevenlabs", voice_id="v-test", model="eleven_multilingual_v2")


async def test_a_cue_per_spoken_beat_on_the_global_timeline(
    make_lesson_contract: Callable[..., SceneContracts], tmp_path
) -> None:
    # Arrange — a real measured manifest (stub TTS), so the cue timestamps follow anim_s.
    contract = make_lesson_contract()
    manifest = await StubSpeechSynthesizer().synthesize(contract, voice=_VOICE, audio_dir=tmp_path)

    # Act
    vtt = build_webvtt(contract, manifest)

    # Assert — header, one cue per spoken beat (silent b3 of each scene emits none), and the cues
    # advance monotonically on the concatenated timeline.
    assert vtt.startswith("WEBVTT\n")
    spoken = [b.narration for s in contract.scenes for b in s.beats if b.narration]
    for text in spoken:
        assert text in vtt
    silent = [b for s in contract.scenes for b in s.beats if not b.narration]
    assert silent, "fixture should include a silent beat to prove it emits no cue"
    assert vtt.count("-->") == len(spoken)
    # Cues advance monotonically on the concatenated timeline (the cursor never resets per scene).
    starts = re.findall(r"(\d{2}:\d{2}:\d{2}\.\d{3}) -->", vtt)
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


def test_cue_timestamps_are_cumulative_webvtt_clocks() -> None:
    # Arrange — a two-beat single scene with known measured windows.
    manifest = TimingManifest(
        {
            "S1_x": SceneTiming(
                beats=[
                    BeatTiming(id="b1", audio_s=3.4, anim_s=3.42, audio="a.mp3", estimated=False),
                    BeatTiming(id="b2", audio_s=5.0, anim_s=5.1, audio="b.mp3", estimated=False),
                ],
                total_s=8.52,
            )
        }
    )
    contract = _single_scene_contract()

    # Act
    vtt = build_webvtt(contract, manifest)

    # Assert — b1 spans 0 → 3.420s, b2 picks up exactly where b1 ended (3.420 → 8.520s).
    assert "00:00:00.000 --> 00:00:03.420" in vtt
    assert "00:00:03.420 --> 00:00:08.520" in vtt


def test_cue_clocks_include_the_per_scene_closing_fade_gap() -> None:
    # Arrange — TWO scenes. Each scene's video ends with a clear_scene fade (SCENE_CLOSE_FADE_S)
    # that plays AFTER its beats, so scene 2's video — and its narration — starts that much later
    # than the sum of scene 1's beat windows. The caption clock must include that gap or it drifts
    # ahead of the video by the fade duration at every scene boundary (the cross-scene drift bug).
    manifest = TimingManifest(
        {
            "S1_a": SceneTiming(
                beats=[
                    BeatTiming(id="b1", audio_s=1.8, anim_s=2.0, audio="a.mp3", estimated=False)
                ],
                total_s=2.0,
            ),
            "S2_b": SceneTiming(
                beats=[
                    BeatTiming(id="b1", audio_s=2.8, anim_s=3.0, audio="b.mp3", estimated=False)
                ],
                total_s=3.0,
            ),
        }
    )
    contract = _two_scene_contract()

    # Act
    vtt = build_webvtt(contract, manifest)

    # Assert — scene 1's cue is 0 → 2.000s; scene 2's cue starts at 2.0 + SCENE_CLOSE_FADE_S, NOT at
    # 2.000s (which is where it would land if the fade gap were ignored — the drift bug).
    assert SCENE_CLOSE_FADE_S == 0.7  # the fade the assert clocks below assume
    assert "00:00:00.000 --> 00:00:02.000" in vtt
    assert "00:00:02.700 --> 00:00:05.700" in vtt  # 2.0 + 0.7 fade → 5.7


def test_a_silent_manifest_has_no_captions() -> None:
    # A silent (estimate) video carries no audio, so it ships no caption cues — just the header.
    contract = _single_scene_contract()
    vtt = build_webvtt(contract, estimate_timing(contract))

    assert vtt.strip() == "WEBVTT"
    assert "-->" not in vtt


def test_a_whitespace_only_beat_emits_no_cue_even_when_voiced() -> None:
    # A beat with a clip but blank (whitespace) narration captions nothing — there are no words.
    contract = _single_scene_contract(first_narration="   ")
    manifest = TimingManifest(
        {
            "S1_x": SceneTiming(
                beats=[
                    BeatTiming(id="b1", audio_s=1.0, anim_s=1.2, audio="a.mp3", estimated=False),
                    BeatTiming(id="b2", audio_s=1.0, anim_s=1.2, audio="b.mp3", estimated=False),
                ],
                total_s=2.4,
            )
        }
    )

    vtt = build_webvtt(contract, manifest)

    # Only the second (spoken) beat cues; the whitespace beat advances the clock silently.
    assert vtt.count("-->") == 1
    assert "The second beat." in vtt


def _two_scene_contract() -> SceneContracts:
    def _scene(scene_id: str, text: str) -> SceneContract:
        return SceneContract(
            id=scene_id,
            archetype="process/flow",
            narration=text,
            objects=["a thing"],
            beats=[Beat(id="b1", action="a", narration=text)],
            sources=["framing only - no empirical claims"],
            duration_s=9,
        )

    return SceneContracts(
        topic="t",
        audience="a",
        visual_archetypes_used=["process/flow"],
        asset_strategy="tier-a procedural",
        global_style=video_global_style(),
        scenes=[_scene("S1_a", "Scene one."), _scene("S2_b", "Scene two.")],
    )


def _single_scene_contract(first_narration: str = "The first beat.") -> SceneContracts:
    scene = SceneContract(
        id="S1_x",
        archetype="process/flow",
        narration="b1 text. b2 text.",
        objects=["a thing"],
        beats=[
            Beat(id="b1", action="a", narration=first_narration),
            Beat(id="b2", action="b", narration="The second beat."),
        ],
        sources=["framing only - no empirical claims"],
        duration_s=9,
    )
    return SceneContracts(
        topic="t",
        audience="a",
        visual_archetypes_used=["process/flow"],
        asset_strategy="tier-a procedural",
        global_style=video_global_style(),
        scenes=[scene],
    )
