from pathlib import Path
from typing import Protocol


class ISyncFrameExtractor(Protocol):
    """Gate D's sampling seam: the single frame at an exact timestamp on the concatenated timeline.

    Kept separate from ``IFrameExtractor`` (Gate B's 30/60/90% scene sampler) so each gate depends
    only on the method it calls (ISP). The concrete ``FrameExtractor`` satisfies both.
    """

    async def extract_at(self, mp4_path: Path, at_seconds: float) -> bytes: ...
