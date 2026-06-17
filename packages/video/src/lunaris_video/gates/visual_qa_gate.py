import asyncio
from pathlib import Path

import structlog

from lunaris_video.errors import SceneRenderError
from lunaris_video.models.rendered_scene import RenderedScene
from lunaris_video.models.scene_qa_result import SceneQaResult
from lunaris_video.protocols.frame_extractor_protocol import IFrameExtractor
from lunaris_video.protocols.scene_code_generator_protocol import ISceneCodeGenerator
from lunaris_video.protocols.scene_renderer_protocol import ISceneRenderer
from lunaris_video.protocols.vision_qa_protocol import IVisionQa
from lunaris_video.schemas import QaDefect, SceneContract, SceneTiming

_logger = structlog.get_logger(__name__)

# The scene is the unit (plan principle 5): a Gate-B defect re-renders ONLY this scene, never the
# video. The skill calibrates 1-3 spatial defects per video, each a one-edit fix; 4 targeted
# repairs is a modest budget before the gate stops and ships the best render it has (the title/hook
# archetypes are the stubborn ones, so the cap was raised from 3 to give them one more chance).
_REPAIR_CAP_PER_SCENE = 4
# One inspection per render: the initial render plus one after each repair.
_INSPECTIONS = _REPAIR_CAP_PER_SCENE + 1


class VisualQaGate:
    """Gate B: extract a rendered scene's frames, judge them with vision, repair targeted defects.

    Per scene: inspect → (if defects) repair the EXACT source → re-render this scene → re-inspect,
    up to the repair cap. A scene that passes ships clean. A scene whose defects survive the budget
    — or whose repair breaks the render — does **not** fail the whole video: the gate *degrades to
    best-effort*, returning the least-defective renderable scene with its unresolved defects on
    record (the 'publish anyway' policy). Returns a ``SceneQaResult``: the render to ship (its
    ``source`` is the source actually on disk) plus any defects it could not clear.
    """

    def __init__(
        self,
        *,
        vision: IVisionQa,
        codegen: ISceneCodeGenerator,
        renderer: ISceneRenderer,
        frames: IFrameExtractor,
    ) -> None:
        self._vision = vision
        self._codegen = codegen
        self._renderer = renderer
        self._frames = frames

    async def inspect_scene(
        self, scene: SceneContract, *, rendered: RenderedScene, timing: SceneTiming, workdir: Path
    ) -> SceneQaResult:
        current = rendered
        # The least-defective renderable scene seen so far, and its defect list — the fallback the
        # gate ships if no render ever passes (rank by defect count; ties keep the earliest render).
        best = rendered
        best_defects: list[QaDefect] | None = None
        for inspection in range(_INSPECTIONS):
            verdict = await self._vision.inspect(
                await self._frames.extract(current.mp4_path), scene
            )
            if verdict.passed:
                _logger.info("visual_qa_gate.scene_passed", scene_id=scene.id, repairs=inspection)
                return SceneQaResult(scene=current)
            if best_defects is None or len(verdict.defects) < len(best_defects):
                best, best_defects = current, verdict.defects
            if inspection == _INSPECTIONS - 1:
                break  # repair budget exhausted — degrade below
            try:
                current = await self._repair_and_rerender(
                    scene, current, defects=verdict.defects, timing=timing, workdir=workdir
                )
            except SceneRenderError:
                # A visual repair that breaks the render: stop and keep the best renderable scene
                # rather than failing the whole video (degrade, not an infinite render loop).
                _logger.warning("visual_qa_gate.repair_broke_render", scene_id=scene.id)
                break
        # ``best_defects`` is set because the loop only reaches here after a failing verdict.
        assert best_defects is not None  # pragma: no cover - guarded by the loop above
        # Targeted repairs could not clear the scene. Before degrading, try ONE simplify pass — drop
        # secondary elements and re-render — because a simpler scene that passes (or has fewer
        # defects) beats shipping a complex, still-defective one.
        simplified = await self._simplify_fallback(
            scene, best=best, best_defects=best_defects, timing=timing, workdir=workdir
        )
        if simplified is not None:
            return simplified
        # Nothing passed within the budget or the simplify pass: ship the best-effort scene with its
        # defects recorded (the 'publish anyway' policy).
        _logger.warning(
            "visual_qa_gate.scene_degraded",
            scene_id=scene.id,
            unresolved_defects=len(best_defects),
            inspections=_INSPECTIONS,
        )
        return SceneQaResult(scene=best, unresolved_defects=tuple(best_defects))

    async def _simplify_fallback(
        self,
        scene: SceneContract,
        *,
        best: RenderedScene,
        best_defects: list[QaDefect],
        timing: SceneTiming,
        workdir: Path,
    ) -> SceneQaResult | None:
        """The last attempt before degrading: regenerate the scene SIMPLER (drop secondary
        elements), re-render and re-inspect. Returns a clean result if it passes, a less-defective
        simpler result if it reduced the defect count, or ``None`` to degrade with ``best`` (the
        simplify broke the render, or did not improve on the loop's best)."""
        try:
            simplified = await self._simplify_and_rerender(
                scene, best, defects=best_defects, timing=timing, workdir=workdir
            )
        except SceneRenderError:
            # A simplify that breaks the render: keep the best prior render rather than fail.
            _logger.warning("visual_qa_gate.simplify_broke_render", scene_id=scene.id)
            return None
        verdict = await self._vision.inspect(await self._frames.extract(simplified.mp4_path), scene)
        if verdict.passed:
            _logger.info("visual_qa_gate.simplify_cleared", scene_id=scene.id)
            return SceneQaResult(scene=simplified)
        if len(verdict.defects) < len(best_defects):
            _logger.info(
                "visual_qa_gate.simplify_reduced_defects",
                scene_id=scene.id,
                before=len(best_defects),
                after=len(verdict.defects),
            )
            return SceneQaResult(scene=simplified, unresolved_defects=tuple(verdict.defects))
        return None  # no better than the loop's best — degrade with that

    async def _repair_and_rerender(
        self,
        scene: SceneContract,
        current: RenderedScene,
        *,
        defects: list[QaDefect],
        timing: SceneTiming,
        workdir: Path,
    ) -> RenderedScene:
        source = await self._codegen.repair_visual(
            scene, source=current.source, defects=defects, timing=timing
        )
        return await self._write_and_render(scene, source, workdir)

    async def _simplify_and_rerender(
        self,
        scene: SceneContract,
        current: RenderedScene,
        *,
        defects: list[QaDefect],
        timing: SceneTiming,
        workdir: Path,
    ) -> RenderedScene:
        source = await self._codegen.simplify_visual(
            scene, source=current.source, defects=defects, timing=timing
        )
        return await self._write_and_render(scene, source, workdir)

    async def _write_and_render(
        self, scene: SceneContract, source: str, workdir: Path
    ) -> RenderedScene:
        scene_file = workdir / f"{scene.id}.py"
        await asyncio.to_thread(scene_file.write_text, source, encoding="utf-8")
        result = await self._renderer.render(scene_file, scene.scene_class_name)
        if not result.succeeded or result.mp4_path is None:
            # A fix that breaks the render: surfaced to the caller, which keeps the prior renderable
            # scene (the degrade fallback) instead of looping or failing the video.
            raise SceneRenderError(scene.id, attempts=1, error_tail=result.error_tail)
        return RenderedScene(scene_id=scene.id, mp4_path=result.mp4_path, source=source)
