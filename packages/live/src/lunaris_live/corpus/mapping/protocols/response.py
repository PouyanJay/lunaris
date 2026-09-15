from typing import Protocol


class IMappingResponse(Protocol):
    @property
    def content(self) -> str | list[object]: ...
