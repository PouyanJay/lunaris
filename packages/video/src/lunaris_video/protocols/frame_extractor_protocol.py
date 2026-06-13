from pathlib import Path
from typing import Protocol


class IFrameExtractor(Protocol):
    """Extracts a scene MP4's QA frames as image bytes — Gate B's sampling seam."""

    async def extract(self, mp4_path: Path) -> list[bytes]: ...
