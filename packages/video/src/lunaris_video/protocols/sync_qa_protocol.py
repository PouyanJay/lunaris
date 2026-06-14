from typing import Protocol

from lunaris_video.schemas import SyncVerdict


class ISyncQa(Protocol):
    """Gate D's vision seam: judge whether one frame shows what a beat's narration describes."""

    async def inspect(self, frame: bytes, *, narration: str, beat_id: str) -> SyncVerdict: ...
