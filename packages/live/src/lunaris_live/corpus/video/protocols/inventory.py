from typing import Protocol

from ..schemas.inventory import VideoInventory


class IVideoInventory(Protocol):
    async def load(self, course_id: str, *, owner_id: str, run_id: str) -> VideoInventory: ...
