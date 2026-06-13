from typing import Protocol

from lunaris_video.schemas import QaVerdict, SceneContract


class IVisionQa(Protocol):
    """Gate B's vision seam: judge a scene's frames against the QA checklist."""

    async def inspect(self, frames: list[bytes], scene: SceneContract) -> QaVerdict: ...
