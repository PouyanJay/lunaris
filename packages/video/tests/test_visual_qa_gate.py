"""Gate B tests: the visual-QA repair loop catches a flagged defect, repairs the EXACT scene
source (never re-plans), re-renders only that scene, and is bounded — a defect no repair fixes
fails clean. Fakes stand in for vision, codegen and the renderer; the loop under test is real."""

from collections.abc import Callable
from pathlib import Path

import pytest
from lunaris_video.errors import SceneQaError
from lunaris_video.gates import VisualQaGate
from lunaris_video.models import RenderedScene, RenderResult
from lunaris_video.schemas import QaDefect, QaVerdict, SceneContract

_DEFECT = QaDefect(issue="blades detached from nacelle", fix_hint="add a pivot anchor")


class _FakeVision:
    """Returns scripted verdicts in order; repeats the last once exhausted."""

    def __init__(self, verdicts: list[QaVerdict]) -> None:
        self.inspected_frames: list[list[bytes]] = []
        self._verdicts = verdicts

    async def inspect(self, frames: list[bytes], scene: SceneContract) -> QaVerdict:
        self.inspected_frames.append(frames)
        return self._verdicts[min(len(self.inspected_frames) - 1, len(self._verdicts) - 1)]


class _FakeFrameExtractor:
    async def extract(self, mp4_path: Path) -> list[bytes]:
        return [b"frame-30", b"frame-60", b"frame-90"]


class _FakeVisualRepairCodegen:
    """Fakes only the visual-repair arm of ISceneCodeGenerator — Gate B never calls generate."""

    def __init__(self) -> None:
        self.visual_repairs: list[list[QaDefect]] = []

    async def repair_visual(
        self, scene: SceneContract, *, source: str, defects: list[QaDefect]
    ) -> str:
        self.visual_repairs.append(defects)
        return f"{source}# visual repair {len(self.visual_repairs)}\n"


class _FakeRenderer:
    def __init__(self) -> None:
        self.renders = 0

    async def render(self, scene_file: Path, scene_class_name: str) -> RenderResult:
        self.renders += 1
        mp4 = scene_file.parent / f"{scene_class_name}.mp4"
        mp4.write_bytes(b"fake")
        return RenderResult(succeeded=True, mp4_path=mp4, error_tail="")


def _rendered(tmp_path: Path) -> RenderedScene:
    mp4 = tmp_path / "S1Problem.mp4"
    mp4.write_bytes(b"fake")
    return RenderedScene(scene_id="S1_problem", mp4_path=mp4, source="# original\n")


def _gate(
    vision: _FakeVision, codegen: _FakeVisualRepairCodegen, renderer: _FakeRenderer
) -> VisualQaGate:
    return VisualQaGate(
        vision=vision, codegen=codegen, renderer=renderer, frames=_FakeFrameExtractor()
    )


async def test_a_clean_scene_passes_without_repair(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange
    vision = _FakeVision([QaVerdict(passed=True)])
    codegen, renderer = _FakeVisualRepairCodegen(), _FakeRenderer()
    gate = _gate(vision, codegen, renderer)

    # Act
    result = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), workdir=tmp_path
    )

    # Assert — inspected once, no repair, the original artifact returned unchanged.
    assert len(vision.inspected_frames) == 1
    assert codegen.visual_repairs == []
    assert result.source == "# original\n"


async def test_a_seeded_defect_is_caught_and_repaired(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — defect on the first look, clean after one repair (the off-pivot-rotation case).
    vision = _FakeVision([QaVerdict(passed=False, defects=[_DEFECT]), QaVerdict(passed=True)])
    codegen, renderer = _FakeVisualRepairCodegen(), _FakeRenderer()
    gate = _gate(vision, codegen, renderer)

    # Act
    result = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), workdir=tmp_path
    )

    # Assert — the defect drove a targeted source repair, re-render, and re-inspection.
    assert codegen.visual_repairs == [[_DEFECT]]
    assert renderer.renders == 1
    assert len(vision.inspected_frames) == 2
    assert result.source.endswith("# visual repair 1\n")


async def test_a_persistent_defect_exhausts_repairs_and_fails_clean(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — every look flags the defect; no repair ever clears it.
    vision = _FakeVision([QaVerdict(passed=False, defects=[_DEFECT])])
    codegen, renderer = _FakeVisualRepairCodegen(), _FakeRenderer()
    gate = _gate(vision, codegen, renderer)
    scene = make_scene(1, "problem")

    # Act
    with pytest.raises(SceneQaError) as excinfo:
        await gate.inspect_scene(scene, rendered=_rendered(tmp_path), workdir=tmp_path)

    # Assert — bounded (3 repairs / 4 inspections), the failure names the unresolved defect.
    assert len(codegen.visual_repairs) == 3
    assert renderer.renders == 3
    assert excinfo.value.scene_id == scene.id
    assert excinfo.value.attempts == 4
    assert "blades detached" in excinfo.value.error_tail
