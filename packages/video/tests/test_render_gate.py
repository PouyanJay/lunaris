"""Gate A tests: the render-repair loop is bounded, evidence-preserving, and fails clean.

The fakes here stand in for the model and the subprocess — the loop logic, budget accounting
and artifact handling under test are the real RenderGate. The real-subprocess path is covered
by test_sandbox.py, and the real-manim path by test_render_smoke.py (skipped where manim is
not installed)."""

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest
from lunaris_video.errors import SceneRenderError
from lunaris_video.gates import RenderGate
from lunaris_video.models import RenderResult
from lunaris_video.schemas import SceneContract, SceneTiming
from lunaris_video.style import render_style_tokens_source

_SOURCE_TEMPLATE = "from manim import *\nfrom style_tokens import *\n# attempt {n}\n"
_ALWAYS_FAIL = 99  # more failures than the repair budget — the renderer never succeeds
# Gate A passes the timing straight to the codegen (the fake ignores it); it never indexes per-beat.
_ANY_TIMING = SceneTiming(beats=[], total_s=0.0)


class _FakeCodegen:
    def __init__(self) -> None:
        self.repair_calls: list[str] = []

    async def generate(self, scene: SceneContract, *, topic: str, timing: SceneTiming) -> str:
        return _SOURCE_TEMPLATE.format(n=0)

    async def repair(
        self, scene: SceneContract, *, source: str, error_tail: str, timing: SceneTiming
    ) -> str:
        self.repair_calls.append(error_tail)
        return _SOURCE_TEMPLATE.format(n=len(self.repair_calls))


class _FakeRenderer:
    """Fails the first ``failures`` renders, then succeeds; records every attempt's source."""

    def __init__(self, failures: int) -> None:
        self._failures = failures
        self.rendered_sources: list[str] = []

    async def render(self, scene_file: Path, scene_class_name: str) -> RenderResult:
        source = await asyncio.to_thread(scene_file.read_text, encoding="utf-8")
        self.rendered_sources.append(source)
        if len(self.rendered_sources) <= self._failures:
            return RenderResult(succeeded=False, mp4_path=None, error_tail="Traceback: boom")
        mp4 = scene_file.parent / f"{scene_class_name}.mp4"
        mp4.write_bytes(b"fake")
        return RenderResult(succeeded=True, mp4_path=mp4, error_tail="")


async def test_first_attempt_success_needs_no_repair(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange
    codegen, renderer = _FakeCodegen(), _FakeRenderer(failures=0)
    gate = RenderGate(codegen=codegen, renderer=renderer)

    # Act
    rendered = await gate.render_scene(
        make_scene(1, "problem"), topic="t", timing=_ANY_TIMING, workdir=tmp_path
    )

    # Assert
    assert rendered.mp4_path.is_file()
    assert codegen.repair_calls == []
    assert rendered.source == _SOURCE_TEMPLATE.format(n=0)


async def test_one_failure_is_repaired_with_the_stack_trace(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange
    codegen, renderer = _FakeCodegen(), _FakeRenderer(failures=1)
    gate = RenderGate(codegen=codegen, renderer=renderer)

    # Act
    rendered = await gate.render_scene(
        make_scene(1, "problem"), topic="t", timing=_ANY_TIMING, workdir=tmp_path
    )

    # Assert — repaired once, the repair saw the trace, the SECOND source rendered.
    assert codegen.repair_calls == ["Traceback: boom"]
    assert renderer.rendered_sources == [
        _SOURCE_TEMPLATE.format(n=0),
        _SOURCE_TEMPLATE.format(n=1),
    ]
    assert rendered.source == _SOURCE_TEMPLATE.format(n=1)


async def test_a_known_bad_scene_exhausts_repairs_and_fails_clean(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — a scene no repair fixes (the renderer never succeeds).
    codegen, renderer = _FakeCodegen(), _FakeRenderer(failures=_ALWAYS_FAIL)
    gate = RenderGate(codegen=codegen, renderer=renderer)
    scene = make_scene(1, "problem")

    # Act
    with pytest.raises(SceneRenderError) as excinfo:
        await gate.render_scene(scene, topic="t", timing=_ANY_TIMING, workdir=tmp_path)

    # Assert — 1 initial + 3 repairs, then a clean failure carrying the evidence; the last
    # attempt's source stays on disk for diagnosis.
    assert len(renderer.rendered_sources) == 4
    assert len(codegen.repair_calls) == 3
    assert excinfo.value.scene_id == scene.id
    assert excinfo.value.attempts == 4
    assert "Traceback: boom" in excinfo.value.error_tail
    on_disk = (tmp_path / f"{scene.id}.py").read_text(encoding="utf-8")
    assert on_disk == _SOURCE_TEMPLATE.format(n=3)


async def test_style_tokens_are_written_beside_the_scenes(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange
    gate = RenderGate(codegen=_FakeCodegen(), renderer=_FakeRenderer(failures=0))

    # Act
    await gate.render_scene(
        make_scene(1, "problem"), topic="t", timing=_ANY_TIMING, workdir=tmp_path
    )

    # Assert — the generated module is written beside the scenes (so `from style_tokens import *`
    # resolves) and IS the canonical generated source. The exact hex values are pinned to
    # index.css by tests/video/test_style_token_drift.py; this test owns placement, not content.
    tokens_file = tmp_path / "style_tokens.py"
    assert tokens_file.read_text(encoding="utf-8") == render_style_tokens_source()
