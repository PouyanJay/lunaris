from typing import Protocol

from ..models.measured_media import MeasuredMedia


class IVideoMedia(Protocol):
    async def inspect(self, *, path: str, max_bytes: int) -> MeasuredMedia: ...
