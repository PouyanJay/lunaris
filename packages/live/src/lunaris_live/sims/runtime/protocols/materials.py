from typing import Protocol

from ....graph import ConceptGraph
from ....session import ISimRegistry
from ..models.preparation import SimPreparation


class ISimMaterials(Protocol):
    async def load(self, graph: ConceptGraph, *, owner_id: str | None) -> ISimRegistry: ...
    async def prepare(self, preparation: SimPreparation) -> None: ...
    async def status(self, graph: ConceptGraph, node_id: str, *, owner_id: str | None) -> str: ...
