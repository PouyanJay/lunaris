from typing import Protocol

from lunaris_video.schemas import QaDefect, SceneContract, SceneTiming


class ISceneCodeGenerator(Protocol):
    """The CODE-stage seam: generation, render repair (Gate A), visual repair (Gate B), and sync
    repair (Gate D).

    ``timing`` is the scene's resolved per-beat windows (audio-drives-video): the generated and
    repaired source must make each beat's animations + waits sum to its window, so the visuals stay
    locked to the narration the manifest measured (or estimated).
    """

    async def generate(self, scene: SceneContract, *, topic: str, timing: SceneTiming) -> str: ...

    async def repair(
        self, scene: SceneContract, *, source: str, error_tail: str, timing: SceneTiming
    ) -> str: ...

    async def repair_visual(
        self, scene: SceneContract, *, source: str, defects: list[QaDefect], timing: SceneTiming
    ) -> str: ...

    async def simplify_visual(
        self, scene: SceneContract, *, source: str, defects: list[QaDefect], timing: SceneTiming
    ) -> str: ...

    async def repair_sync(
        self, scene: SceneContract, *, source: str, beat_id: str, reason: str, timing: SceneTiming
    ) -> str: ...
