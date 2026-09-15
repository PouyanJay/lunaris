from typing import Protocol

from .response import IMappingResponse


class IMappingModel(Protocol):
    async def ainvoke(self, prompt: str) -> IMappingResponse: ...
