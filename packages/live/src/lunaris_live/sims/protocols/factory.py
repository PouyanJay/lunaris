from typing import Protocol

from ...graph import ConceptNode, MasteryCriterion
from ..schema.build_result import SimBuildResult


class ISimFactory(Protocol):
    async def build(
        self, node: ConceptNode, criterion: MasteryCriterion, *, run_id: str
    ) -> SimBuildResult: ...
