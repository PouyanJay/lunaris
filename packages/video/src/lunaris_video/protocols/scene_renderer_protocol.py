from pathlib import Path
from typing import Protocol

from lunaris_video.models.render_result import RenderResult


class ISceneRenderer(Protocol):
    """Renders one scene class from a scene file — the subprocess seam Gate A drives."""

    async def render(self, scene_file: Path, scene_class_name: str) -> RenderResult: ...
