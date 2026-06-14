from pathlib import Path
from typing import Protocol


class IFrameExtractor(Protocol):
    """Extracts a scene MP4's QA frames as image bytes — Gate B's sampling seam.

    Gate D's single-frame-at-a-timestamp need is a separate seam (``ISyncFrameExtractor``) so each
    gate depends only on the method it calls; the concrete ``FrameExtractor`` satisfies both.
    """

    async def extract(self, mp4_path: Path) -> list[bytes]: ...
