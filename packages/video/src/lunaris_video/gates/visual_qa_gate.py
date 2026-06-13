import asyncio
from pathlib import Path

import structlog

from lunaris_video.errors import SceneQaError, SceneRenderError
from lunaris_video.models.rendered_scene import RenderedScene
from lunaris_video.protocols.frame_extractor_protocol import IFrameExtractor
from lunaris_video.protocols.scene_code_generator_protocol import ISceneCodeGenerator
from lunaris_video.protocols.scene_renderer_protocol import ISceneRenderer
from lunaris_video.protocols.vision_qa_protocol import IVisionQa
from lunaris_video.schemas import QaDefect, SceneContract

_logger = structlog.get_logger(__name__)

# The scene is the unit (plan principle 5): a Gate-B defect re-renders ONLY this scene, never the
# video. The skill calibrates 1-3 spatial defects per video, each a one-edit fix; 3 targeted
# repairs is the matching budget before the job fails cleanly (no auto-simplify).
_REPAIR_CAP_PER_SCENE = 3
# One inspection per render: the initial render plus one after each repair.
_INSPECTIONS = _REPAIR_CAP_PER_SCENE + 1


class VisualQaGate:
    """Gate B: extract a rendered scene's frames, judge them with vision, repair targeted defects.

    Per scene: inspect → (if defects) repair the EXACT source → re-render this scene → re-inspect,
    up to 3 repairs. A visual repair that breaks the render, or a defect that survives the budget,
    raises ``SceneQaError`` — the job fails with the unresolved defects on record. Returns the
    cleared ``RenderedScene`` (its ``source`` is the repaired source actually on disk).
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
        self, scene: SceneContract, *, rendered: RenderedScene, workdir: Path
    ) -> RenderedScene:
        current = rendered
        for inspection in range(_INSPECTIONS):
            verdict = await self._vision.inspect(
                await self._frames.extract(current.mp4_path), scene
            )
            if verdict.passed:
                _logger.info("visual_qa_gate.scene_passed", scene_id=scene.id, repairs=inspection)
                return current
            is_last_inspection = inspection == _INSPECTIONS - 1
            if is_last_inspection:
                raise SceneQaError(
                    scene.id, attempts=_INSPECTIONS, error_tail=_defects_tail(verdict.defects)
                )
            current = await self._repair_and_rerender(
                scene, current, defects=verdict.defects, workdir=workdir
            )
        raise AssertionError("unreachable")  # pragma: no cover

    async def _repair_and_rerender(
        self,
        scene: SceneContract,
        current: RenderedScene,
        *,
        defects: list[QaDefect],
        workdir: Path,
    ) -> RenderedScene:
        source = await self._codegen.repair_visual(scene, source=current.source, defects=defects)
        scene_file = workdir / f"{scene.id}.py"
        await asyncio.to_thread(scene_file.write_text, source, encoding="utf-8")
        result = await self._renderer.render(scene_file, scene.scene_class_name)
        if not result.succeeded or result.mp4_path is None:
            # A visual fix that breaks the render is a clean failure, not an infinite render loop.
            raise SceneRenderError(scene.id, attempts=1, error_tail=result.error_tail)
        return RenderedScene(scene_id=scene.id, mp4_path=result.mp4_path, source=source)


def _defects_tail(defects: list[QaDefect]) -> str:
    return "; ".join(defect.issue for defect in defects)
