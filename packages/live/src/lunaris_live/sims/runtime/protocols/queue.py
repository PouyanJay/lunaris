from typing import Protocol

from ..schema.job import SimJob
from ..schema.request import SimRequest


class ISimQueue(Protocol):
    def enqueue(self, request: SimRequest, *, session_id: str, owner_id: str) -> str: ...
    def take(self) -> SimJob | None: ...
    def status(self, cache_key: str, *, owner_id: str) -> str: ...
