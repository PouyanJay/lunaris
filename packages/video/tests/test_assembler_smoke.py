"""Real-ffmpeg assembly smoke: render two scenes, concat them stream-copy into one MP4, extract a
poster, and bundle timing/contracts. Self-skips where the render extra is absent."""

import importlib.util
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from lunaris_video.assembly import SCENE_CLOSE_FADE_S, VideoAssembler, estimate_timing
from lunaris_video.gates import ensure_style_tokens
from lunaris_video.models import RenderedScene
from lunaris_video.rendering import SceneRenderer
from lunaris_video.schemas import (
    Beat,
    BeatTiming,
    SceneContract,
    SceneContracts,
    SceneTiming,
    TimingManifest,
)
from lunaris_video.style import video_global_style

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("manim") is None,
    reason="render extra not installed (make video-deps)",
)

_SCENE = """\
from manim import *
from style_tokens import *


class {cls}(Scene):
    def construct(self):
        t = Text("{label}", font_size=30, color=INK, font=FONT)
        self.add(t)
        self.wait(0.4)
        self.play(FadeOut(t), run_time=0.2)
"""


async def _render(workdir: Path, scene_id: str, cls: str, label: str) -> RenderedScene:
    ensure_style_tokens(workdir)
    scene_file = workdir / f"{scene_id}.py"
    scene_file.write_text(_SCENE.format(cls=cls, label=label), encoding="utf-8")
    result = await SceneRenderer().render(scene_file, cls)
    assert result.succeeded, result.error_tail
    return RenderedScene(scene_id=scene_id, mp4_path=result.mp4_path, source="")


async def test_two_scenes_assemble_into_one_video(
    make_lesson_contract: Callable[..., SceneContracts], tmp_path: Path
) -> None:
    # Arrange — two real per-scene renders.
    scenes = [
        await _render(tmp_path, "S1_intro", "S1Intro", "one"),
        await _render(tmp_path, "S2_body", "S2Body", "two"),
    ]
    contract = make_lesson_contract()

    # Act — the assembler persists the SAME manifest the render was built against, never re-derives.
    video = await VideoAssembler().assemble(
        scenes, contract, manifest=estimate_timing(contract), workdir=tmp_path
    )

    # Assert — a real concatenated MP4, a real JPEG poster, and the regeneration manifests. The
    # manifests pin that BOTH scenes made it into the bundle, not just that some bytes were emitted.
    assert video.mp4[4:8] == b"ftyp"
    assert video.poster[:3] == b"\xff\xd8\xff"
    assert len(video.mp4) > sum(s.mp4_path.stat().st_size for s in scenes) * 0.5
    contracts = json.loads(video.contracts_json)
    assert len(contracts["scenes"]) == len(contract.scenes)
    timing = json.loads(video.timing_json)
    assert len(timing) == len(contract.scenes)
    # The silent path mints no audio and no captions.
    assert video.captions is None
    assert _audio_stream_count(video.mp4, tmp_path) == 0


async def test_a_voiced_manifest_muxes_narration_and_emits_captions(tmp_path: Path) -> None:
    # Arrange — one real render, one real (silent) TTS clip, and a voiced manifest referencing it.
    scene = await _render(tmp_path, "S1_x", "S1X", "hello")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    _make_silence(audio_dir / "S1_x_b1.mp3", seconds=1.0)
    contract, manifest = _voiced_fixture()

    # Act
    video = await VideoAssembler().assemble(
        [scene], contract, manifest=manifest, workdir=tmp_path, audio_dir=audio_dir
    )

    # Assert — the muxed MP4 carries exactly one audio stream, and a WebVTT track shipped.
    assert _audio_stream_count(video.mp4, tmp_path) == 1
    assert video.captions is not None
    assert video.captions.startswith(b"WEBVTT")
    assert b"-->" in video.captions  # a structurally valid cue block, not a bare header
    assert b"Hello world." in video.captions


async def test_the_narration_track_is_exactly_video_length_across_a_scene_boundary(
    tmp_path: Path,
) -> None:
    # Real ffmpeg: a TWO-scene voiced manifest mixed through the real amix/concat filtergraph. The
    # narration track must be exactly as long as the concatenated video — every beat window PLUS one
    # closing-fade tail per scene — so the audio never drifts at a scene boundary (the drift bug).
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    _make_silence(audio_dir / "S1_b1.mp3", seconds=1.8)
    _make_silence(audio_dir / "S2_b1.mp3", seconds=2.8)
    manifest = TimingManifest(
        {
            "S1_a": SceneTiming(
                beats=[
                    BeatTiming(id="b1", audio_s=1.8, anim_s=2.0, audio="S1_b1.mp3", estimated=False)
                ],
                total_s=2.0,
            ),
            "S2_b": SceneTiming(
                beats=[
                    BeatTiming(
                        id="b1", audio_s=2.8, anim_s=3.0, audio="S2_b1.mp3", estimated=False
                    ),
                    BeatTiming(id="b2", audio_s=0.0, anim_s=1.5, audio=None, estimated=False),
                ],
                total_s=4.5,
            ),
        }
    )
    out_wav = tmp_path / "narration.wav"

    # Act — the real mixer.
    await VideoAssembler()._mix_audio(manifest, audio_dir, out_wav, workdir=tmp_path)

    # Assert — every beat window (2.0 + 3.0 + 1.5) plus one closing fade per scene (2 x 0.7) = the
    # video's length; the boundary fade tail is what keeps the second scene's audio from starting
    # early. Sample-exact PCM, so the residual is well under a frame.
    expected = 2.0 + 3.0 + 1.5 + 2 * SCENE_CLOSE_FADE_S
    assert abs(_probe_duration(out_wav) - expected) < 0.05


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return float(out.stdout.strip())


def _make_silence(path: Path, *, seconds: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=stereo", "-t", str(seconds), str(path)],
        check=True,
    )  # fmt: skip


def _audio_stream_count(mp4: bytes, tmp_path: Path) -> int:
    probe = tmp_path / "probe.mp4"
    probe.write_bytes(mp4)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(probe)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return len([line for line in out.stdout.splitlines() if line.strip()])


def _voiced_fixture() -> tuple[SceneContracts, TimingManifest]:
    scene = SceneContract(
        id="S1_x",
        archetype="process/flow",
        narration="Hello world.",
        objects=["a greeting"],
        beats=[Beat(id="b1", action="text fades in", narration="Hello world.")],
        sources=["framing only - no empirical claims"],
        duration_s=2,
    )
    contract = SceneContracts(
        topic="t",
        audience="a",
        visual_archetypes_used=["process/flow"],
        asset_strategy="tier-a procedural",
        global_style=video_global_style(),
        scenes=[scene],
    )
    manifest = TimingManifest(
        {
            "S1_x": SceneTiming(
                beats=[
                    BeatTiming(
                        id="b1", audio_s=1.0, anim_s=1.2, audio="S1_x_b1.mp3", estimated=False
                    )
                ],
                total_s=1.2,
            )
        }
    )
    return contract, manifest
