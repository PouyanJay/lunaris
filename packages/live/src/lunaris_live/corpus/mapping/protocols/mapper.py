from typing import Protocol

from ....graph.schema import ConceptGraph
from ..models.request import MappingRequest


class IAssetMapper(Protocol):
    async def map(self, request: MappingRequest) -> ConceptGraph: ...
