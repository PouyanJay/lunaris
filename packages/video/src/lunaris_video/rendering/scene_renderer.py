import sys
from pathlib import Path

import structlog

from lunaris_video.models.render_result import RenderResult
from lunaris_video.models.sandbox_result import SandboxResult
from lunaris_video.rendering.mp4_path import expected_scene_mp4
from lunaris_video.rendering.sandbox import run_sandboxed

_logger = structlog.get_logger(__name__)

# The skill's validated render profile: 720p30, caching off (cache reuse across generated code
# is a correctness hazard — partial-movie caches key on code that the repair loop rewrites).
_QUALITY_FLAG = "-qm"
_DEFAULT_TIMEOUT_S = 300.0


class SceneRenderer:
    """Renders ONE scene class from a scene file via Manim CE, inside the sandbox.

    Runs ``python -m manim`` from THIS interpreter (the venv that owns the render extra), with
    cwd = the scene file's directory so the generated module finds ``style_tokens.py`` beside
    it. Media lands under ``<workdir>/media``; success is the expected MP4 existing, not just a
    zero exit (manim can exit 0 on a no-op).
    """

    def __init__(self, *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s

    async def render(self, scene_file: Path, scene_class_name: str) -> RenderResult:
        workdir = scene_file.parent
        argv = [
            sys.executable,
            "-m",
            "manim",
            "render",
            _QUALITY_FLAG,
            "--disable_caching",
            "--media_dir",
            "media",
            scene_file.name,
            scene_class_name,
        ]
        result = await run_sandboxed(argv, cwd=workdir, timeout_s=self._timeout_s)
        mp4_path = expected_scene_mp4(scene_file, scene_class_name)
        if result.succeeded and mp4_path.is_file():
            _logger.info("scene_renderer.rendered", scene_class=scene_class_name)
            return RenderResult(succeeded=True, mp4_path=mp4_path, error_tail="")
        error_tail = _compose_error_tail(result, mp4_path)
        _logger.warning(
            "scene_renderer.render_failed",
            scene_class=scene_class_name,
            returncode=result.returncode,
            timed_out=result.timed_out,
        )
        return RenderResult(succeeded=False, mp4_path=None, error_tail=error_tail)


def _compose_error_tail(result: SandboxResult, mp4_path: Path) -> str:
    if result.succeeded and not mp4_path.is_file():
        return f"manim exited 0 but produced no {mp4_path.name} — wrong class name or empty scene"
    return f"{result.stderr_tail}\n{result.stdout_tail}".strip()
