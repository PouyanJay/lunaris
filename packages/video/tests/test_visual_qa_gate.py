"""Gate B tests: the visual-QA repair loop catches a flagged defect, repairs the EXACT scene
source (never re-plans), re-renders only that scene, and is bounded. A defect no repair clears no
longer fails the whole video — the gate DEGRADES to best-effort, keeping the least-defective
renderable scene and recording the unresolved defects (the 'publish anyway' policy). Fakes stand in
for vision, codegen and the renderer; the loop under test is real."""

from collections.abc import Callable
from pathlib import Path

from lunaris_video.gates import VisualQaGate
from lunaris_video.models import RenderedScene, RenderResult, SceneQaResult
from lunaris_video.schemas import QaDefect, QaVerdict, SceneContract, SceneTiming

_DEFECT = QaDefect(issue="blades detached from nacelle", fix_hint="add a pivot anchor")
# Gate B passes the scene timing straight to the visual-repair codegen (which the fake ignores) — it
# never indexes per-beat, so any valid manifest entry exercises the loop under test.
_ANY_TIMING = SceneTiming(beats=[], total_s=0.0)


def _verdict(defect_count: int) -> QaVerdict:
    """A failing verdict carrying exactly ``defect_count`` distinct defects (rank-by-count fuel)."""
    return QaVerdict(
        passed=False,
        defects=[QaDefect(issue=f"defect {i}", fix_hint="fix it") for i in range(defect_count)],
    )


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
        self, scene: SceneContract, *, source: str, defects: list[QaDefect], timing: SceneTiming
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


class _RendererFailingAfter:
    """Succeeds for the first ``ok`` renders, then fails — to model a visual repair that breaks
    the render (the degrade path must keep the best prior renderable scene, not raise)."""

    def __init__(self, ok: int) -> None:
        self.renders = 0
        self._ok = ok

    async def render(self, scene_file: Path, scene_class_name: str) -> RenderResult:
        self.renders += 1
        if self.renders > self._ok:
            return RenderResult(succeeded=False, mp4_path=None, error_tail="manim: blew up")
        mp4 = scene_file.parent / f"{scene_class_name}.mp4"
        mp4.write_bytes(b"fake")
        return RenderResult(succeeded=True, mp4_path=mp4, error_tail="")


def _rendered(tmp_path: Path) -> RenderedScene:
    mp4 = tmp_path / "S1Problem.mp4"
    mp4.write_bytes(b"fake")
    return RenderedScene(scene_id="S1_problem", mp4_path=mp4, source="# original\n")


def _gate(vision: _FakeVision, codegen: _FakeVisualRepairCodegen, renderer: object) -> VisualQaGate:
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
        make_scene(1, "problem"), rendered=_rendered(tmp_path), timing=_ANY_TIMING, workdir=tmp_path
    )

    # Assert — inspected once, no repair, the original artifact returned clean (no defects).
    assert isinstance(result, SceneQaResult)
    assert len(vision.inspected_frames) == 1
    assert codegen.visual_repairs == []
    assert result.scene.source == "# original\n"
    assert result.unresolved_defects == ()


async def test_a_seeded_defect_is_caught_and_repaired(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — defect on the first look, clean after one repair (the off-pivot-rotation case).
    vision = _FakeVision([QaVerdict(passed=False, defects=[_DEFECT]), QaVerdict(passed=True)])
    codegen, renderer = _FakeVisualRepairCodegen(), _FakeRenderer()
    gate = _gate(vision, codegen, renderer)

    # Act
    result = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), timing=_ANY_TIMING, workdir=tmp_path
    )

    # Assert — the defect drove a targeted source repair, re-render, and re-inspection; the cleared
    # scene ships with no unresolved defects.
    assert codegen.visual_repairs == [[_DEFECT]]
    assert renderer.renders == 1
    assert len(vision.inspected_frames) == 2
    assert result.scene.source.endswith("# visual repair 1\n")
    assert result.unresolved_defects == ()


async def test_a_persistent_defect_degrades_to_best_effort(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — every look flags the defect; no repair ever clears it.
    vision = _FakeVision([QaVerdict(passed=False, defects=[_DEFECT])])
    codegen, renderer = _FakeVisualRepairCodegen(), _FakeRenderer()
    gate = _gate(vision, codegen, renderer)
    scene = make_scene(1, "problem")

    # Act — the whole video is NEVER failed on one stubborn scene (no SceneQaError raised).
    result = await gate.inspect_scene(
        scene, rendered=_rendered(tmp_path), timing=_ANY_TIMING, workdir=tmp_path
    )

    # Assert — bounded at the per-scene cap (4 repairs / 5 inspections), then degrades: the best
    # renderable scene ships with the unresolved defect recorded.
    assert len(codegen.visual_repairs) == 4
    assert renderer.renders == 4
    assert len(vision.inspected_frames) == 5
    assert result.unresolved_defects == (_DEFECT,)
    assert result.scene.source  # a real renderable scene is kept, not None


async def test_degrade_keeps_the_least_defective_render(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — defect counts 3 → 1 → 2 (→2…): the render at the 1-defect look is the best one.
    vision = _FakeVision([_verdict(3), _verdict(1), _verdict(2)])
    codegen, renderer = _FakeVisualRepairCodegen(), _FakeRenderer()
    gate = _gate(vision, codegen, renderer)

    # Act
    result = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), timing=_ANY_TIMING, workdir=tmp_path
    )

    # Assert — the kept render is the one with the fewest defects (the source after repair #1), and
    # its single unresolved defect (not the 3- or 2-defect verdicts) is what is recorded.
    assert result.scene.source.endswith("# visual repair 1\n")
    assert "# visual repair 2" not in result.scene.source
    assert len(result.unresolved_defects) == 1


async def test_a_repair_that_breaks_the_render_keeps_the_best_prior_render(
    make_scene: Callable[..., SceneContract], tmp_path: Path
) -> None:
    # Arrange — the scene renders defective; the first visual repair breaks the render entirely.
    vision = _FakeVision([QaVerdict(passed=False, defects=[_DEFECT])])
    codegen, renderer = _FakeVisualRepairCodegen(), _RendererFailingAfter(ok=0)
    gate = _gate(vision, codegen, renderer)

    # Act — a repair that breaks the render must NOT fail the video; it stops and keeps the best
    # renderable scene seen so far (the original render).
    result = await gate.inspect_scene(
        make_scene(1, "problem"), rendered=_rendered(tmp_path), timing=_ANY_TIMING, workdir=tmp_path
    )

    # Assert — one (failed) repair-render attempt, then degrade to the original renderable scene.
    assert renderer.renders == 1
    assert result.scene.source == "# original\n"
    assert result.unresolved_defects == (_DEFECT,)
