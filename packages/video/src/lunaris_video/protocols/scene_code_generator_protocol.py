from typing import Protocol

from lunaris_video.schemas import QaDefect, SceneContract


class ISceneCodeGenerator(Protocol):
    """The CODE-stage seam: generation, render repair (Gate A), and visual repair (Gate B)."""

    async def generate(self, scene: SceneContract, *, topic: str) -> str: ...

    async def repair(self, scene: SceneContract, *, source: str, error_tail: str) -> str: ...

    async def repair_visual(
        self, scene: SceneContract, *, source: str, defects: list[QaDefect]
    ) -> str: ...
