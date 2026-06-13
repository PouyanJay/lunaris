from pathlib import Path
from typing import Protocol

from lunaris_video.models import RenderedScene, RenderedVideo
from lunaris_video.schemas import VideoContract


class IVideoAssembler(Protocol):
    """Stage 4 seam: cleared per-scene MP4s + contract → the finished artifact bundle."""

    async def assemble(
        self, scenes: list[RenderedScene], contract: VideoContract, *, workdir: Path
    ) -> RenderedVideo: ...
