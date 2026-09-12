from typing import Protocol

from ..models.completion import SimCompletion


class ISimModel(Protocol):
    @property
    def model_name(self) -> str: ...

    async def complete(
        self, prompt: str, *, max_tokens: int, images: list[str] | None = None
    ) -> SimCompletion: ...
