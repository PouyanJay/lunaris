"""Hermetic audio-mix tests: the per-beat + per-scene-fade segment plan the mixer builds (no ffmpeg
needed — the real mix is the assembler smoke). Here we pin the segment GEOMETRY that keeps the audio
track exactly as long as the video, scene for scene, so narration never drifts at a boundary."""

import re

from lunaris_video.assembly import SCENE_CLOSE_FADE_S
from lunaris_video.assembly.video_assembler import _audio_segments
from lunaris_video.schemas import BeatTiming, SceneTiming, TimingManifest
from lunaris_video.skill import read_skill_asset


def test_scene_close_fade_matches_clear_scene_default_run_time() -> None:
    # The audio tail + caption gap + length gate all assume the scene's closing fade is exactly
    # SCENE_CLOSE_FADE_S. That MUST equal clear_scene's default run_time in the pinned style_tokens:
    # if the skill changes the fade and this constant doesn't, audio/captions drift again. Pin them.
    style_tokens = read_skill_asset("assets/style_tokens.py")
    match = re.search(r"def clear_scene\(scene, run_time=([0-9.]+)\)", style_tokens)
    assert match, (
        "clear_scene signature changed — re-pin SCENE_CLOSE_FADE_S to its run_time default"
    )
    assert float(match.group(1)) == SCENE_CLOSE_FADE_S


def test_audio_segments_pad_each_scene_with_its_closing_fade() -> None:
    # Arrange — two scenes; scene 2 has a trailing SILENT beat as well as its spoken one.
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
                    BeatTiming(id="b1", audio_s=2.8, anim_s=3.0, audio="b.mp3", estimated=False),
                    BeatTiming(id="b2", audio_s=0.0, anim_s=1.5, audio=None, estimated=False),
                ],
                total_s=4.5,
            ),
        }
    )

    # Act
    segments = [(seg.clip, round(seg.seconds, 3)) for seg in _audio_segments(manifest)]

    # Assert — each beat occupies exactly its anim_s window (a clip or silence), and EACH scene is
    # followed by a SCENE_CLOSE_FADE_S silent span matching the render's closing fade.
    assert segments == [
        ("a.mp3", 2.0),
        (None, SCENE_CLOSE_FADE_S),  # scene 1's closing fade
        ("b.mp3", 3.0),
        (None, 1.5),  # scene 2's silent beat
        (None, SCENE_CLOSE_FADE_S),  # scene 2's closing fade
    ]
    # The whole track equals every beat window plus one closing fade per scene — i.e. the video's
    # length (each scene's video is total_s + the fade), so |audio - video| is only frame jitter.
    total = sum(seg.seconds for seg in _audio_segments(manifest))
    assert round(total, 3) == round(2.0 + 3.0 + 1.5 + 2 * SCENE_CLOSE_FADE_S, 3)
