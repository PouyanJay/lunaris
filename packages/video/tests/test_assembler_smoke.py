"""Real-ffmpeg assembly smoke: render two scenes, concat them stream-copy into one MP4, extract a
poster, and bundle timing/contracts. Self-skips where the render extra is absent."""

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from lunaris_video.assembly import VideoAssembler, estimate_timing
from lunaris_video.gates import ensure_style_tokens
from lunaris_video.models import RenderedScene
from lunaris_video.rendering import SceneRenderer
from lunaris_video.schemas import SceneContracts

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
