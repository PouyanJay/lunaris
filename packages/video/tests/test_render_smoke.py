"""Real-manim render smoke tests — truth is what runs.

These exercise the actual subprocess path: real ``python -m manim`` inside the sandbox, real
MP4 bytes, real stack traces feeding the repair loop. They self-skip where the render extra is
not installed (CI installs without extras; `make video-deps` makes a dev machine capable)."""

import importlib.util
from collections.abc import Callable
from pathlib import Path

import pytest
from lunaris_video.errors import SceneRenderError
from lunaris_video.gates import RenderGate, ensure_style_tokens
from lunaris_video.rendering import SceneRenderer
from lunaris_video.schemas import SceneContract, SceneTiming

# Gate A passes the timing straight to the scripted codegen (which ignores it); never indexed.
_ANY_TIMING = SceneTiming(beats=[], total_s=0.0)

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("manim") is None,
    reason="render extra not installed (make video-deps)",
)

_SMOKE_TIMEOUT_S = 120  # test-environment render budget; the production default is 300s

_GOOD_SCENE = """\
from manim import *
from style_tokens import *


class S1Problem(Scene):
    def construct(self):
        title = Text("smoke", font_size=30, color=INK, font=FONT)
        self.add(title)
        self.wait(0.2)
        self.play(FadeOut(title), run_time=0.2)
"""

_BROKEN_SCENE = """\
from manim import *
from style_tokens import *


class S1Problem(Scene):
    def construct(self):
        raise RuntimeError("seeded render failure S1")
"""


class _ScriptedCodegen:
    """Emits a fixed source; 'repairs' by emitting it again (an unfixable scene)."""

    def __init__(self, source: str) -> None:
        self._source = source
        self.repair_tails: list[str] = []

    async def generate(self, scene: SceneContract, *, topic: str, timing: SceneTiming) -> str:
        return self._source

    async def repair(
        self, scene: SceneContract, *, source: str, error_tail: str, timing: SceneTiming
    ) -> str:
        self.repair_tails.append(error_tail)
        return self._source


async def test_a_real_scene_renders_to_a_real_mp4(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange
    ensure_style_tokens(tmp_path)
    scene_file = tmp_path / "S1_problem.py"
    scene_file.write_text(_GOOD_SCENE, encoding="utf-8")

    # Act
    result = await SceneRenderer().render(scene_file, "S1Problem")

    # Assert — honest media from the honest toolchain.
    assert result.succeeded, result.error_tail
    assert result.mp4_path is not None
    header = result.mp4_path.read_bytes()[:64]
    assert b"ftyp" in header


async def test_a_known_bad_scene_exhausts_repairs_against_real_manim(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — codegen that can never fix its scene; the REAL renderer produces the traces.
    # No ensure_style_tokens() call here (unlike the good-scene test): RenderGate writes the
    # tokens file itself before the first render.
    codegen = _ScriptedCodegen(_BROKEN_SCENE)
    gate = RenderGate(codegen=codegen, renderer=SceneRenderer(timeout_s=_SMOKE_TIMEOUT_S))

    # Act
    with pytest.raises(SceneRenderError) as excinfo:
        await gate.render_scene(
            make_scene(1, "problem"), topic="t", timing=_ANY_TIMING, workdir=tmp_path
        )

    # Assert — every repair turn saw the real seeded stack trace; the failure is clean and
    # carries the evidence.
    assert excinfo.value.attempts == 4
    assert "seeded render failure S1" in excinfo.value.error_tail
    assert len(codegen.repair_tails) == 3
    assert all("seeded render failure S1" in tail for tail in codegen.repair_tails)
