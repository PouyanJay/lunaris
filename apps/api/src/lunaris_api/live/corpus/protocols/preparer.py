from typing import Protocol

from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_live.graph import ConceptGraph


class ICorpusGraphPreparer(Protocol):
    async def prepare(
        self, graph: ConceptGraph, *, snapshot: CorpusSnapshot, owner_id: str
    ) -> ConceptGraph: ...
