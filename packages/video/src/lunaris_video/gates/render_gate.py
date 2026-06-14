import asyncio
from pathlib import Path

import structlog

from lunaris_video.errors import SceneRenderError
from lunaris_video.gates.style_tokens_writer import ensure_style_tokens
from lunaris_video.models.rendered_scene import RenderedScene
from lunaris_video.protocols.scene_code_generator_protocol import ISceneCodeGenerator
from lunaris_video.protocols.scene_renderer_protocol import ISceneRenderer
from lunaris_video.schemas import SceneContract, SceneTiming

_logger = structlog.get_logger(__name__)

# The skill's calibrated budget: with the patterns discipline, first-attempt success is the
# norm and 3 stack-trace-driven repairs catch the rest. Beyond that the scene is structurally
# broken — fail the job cleanly (no auto-simplify; the regenerate menu owns that, plan §1.2).
_REPAIR_CAP_PER_SCENE = 3
_TOTAL_RENDER_BUDGET = 1 + _REPAIR_CAP_PER_SCENE
# A failed render's trace goes to the job error in full; the warning log keeps only a short tail
# so a render storm can't bloat structured-log payloads.
_LOG_ERROR_TAIL_CHARS = 500


class RenderGate:
    """Gate A: generate a scene's code, render it, and repair from the stack trace — bounded.

    Per scene: 1 initial render + up to 3 repair renders. Every attempt's source stays on disk
    in the scene's workdir (``<id>.py`` is overwritten in place; the final state is whatever
    last ran, so a failed job's evidence is inspectable). Raises ``SceneRenderError`` when the
    budget is exhausted — the pipeline fails the job; partial videos are unrepresentable.
    """

    def __init__(self, *, codegen: ISceneCodeGenerator, renderer: ISceneRenderer) -> None:
        self._codegen = codegen
        self._renderer = renderer

    async def render_scene(
        self, scene: SceneContract, *, topic: str, timing: SceneTiming, workdir: Path
    ) -> RenderedScene:
        await asyncio.to_thread(ensure_style_tokens, workdir)
        scene_file = workdir / f"{scene.id}.py"
        source = await self._codegen.generate(scene, topic=topic, timing=timing)
        for attempt in range(1, _TOTAL_RENDER_BUDGET + 1):
            await asyncio.to_thread(scene_file.write_text, source, encoding="utf-8")
            result = await self._renderer.render(scene_file, scene.scene_class_name)
            if result.succeeded and result.mp4_path is not None:
                _logger.info("render_gate.scene_passed", scene_id=scene.id, attempt=attempt)
                return RenderedScene(scene_id=scene.id, mp4_path=result.mp4_path, source=source)
            _logger.warning(
                "render_gate.render_failed",
                scene_id=scene.id,
                attempt=attempt,
                error_tail=result.error_tail[-_LOG_ERROR_TAIL_CHARS:],
            )
            if attempt == _TOTAL_RENDER_BUDGET:
                raise SceneRenderError(
                    scene.id, attempts=_TOTAL_RENDER_BUDGET, error_tail=result.error_tail
                )
            source = await self._codegen.repair(
                scene, source=source, error_tail=result.error_tail, timing=timing
            )
        raise AssertionError("unreachable")  # pragma: no cover
