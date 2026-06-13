from typing import Protocol

from lunaris_video.schemas import SceneContract


class ISceneCodeGenerator(Protocol):
    """The CODE stage seam: initial generation plus stack-trace-driven render repair."""

    async def generate(self, scene: SceneContract, *, topic: str) -> str: ...

    async def repair(self, scene: SceneContract, *, source: str, error_tail: str) -> str: ...
