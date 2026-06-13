"""Real-ffmpeg frame-extraction smoke test — truth is what runs.

Renders a real scene, then extracts the 30/60/90% frames with real ffmpeg and asserts three
honest PNGs come back. Self-skips where the render extra is absent (CI installs without it)."""

import importlib.util
from collections.abc import Callable
from pathlib import Path

import pytest
from lunaris_video.gates import ensure_style_tokens
from lunaris_video.rendering import FrameExtractor, SceneRenderer
from lunaris_video.schemas import SceneContract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("manim") is None,
    reason="render extra not installed (make video-deps)",
)

_SCENE = """\
from manim import *
from style_tokens import *


class S1Problem(Scene):
    def construct(self):
        title = Text("frames", font_size=30, color=INK, font=FONT)
        self.add(title)
        self.wait(0.5)
        self.play(FadeOut(title), run_time=0.3)
"""

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


async def test_three_frames_are_extracted_from_a_real_render(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — a real rendered scene (the guard surfaces manim's error tail if the render breaks).
    ensure_style_tokens(tmp_path)
    scene_file = tmp_path / "S1_problem.py"
    scene_file.write_text(_SCENE, encoding="utf-8")
    render = await SceneRenderer().render(scene_file, "S1Problem")
    assert render.succeeded, render.error_tail

    # Act
    frames = await FrameExtractor().extract(render.mp4_path)

    # Assert — three honest PNGs (30/60/90%), each non-trivial.
    assert len(frames) == 3
    for frame in frames:
        assert frame[:8] == _PNG_MAGIC
        assert len(frame) > 1000
