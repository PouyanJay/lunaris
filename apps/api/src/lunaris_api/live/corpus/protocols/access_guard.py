from typing import Protocol

from lunaris_live.graph import ConceptGraph

from ..models.access_policy import CorpusAccessPolicy


class ICorpusAccessGuard(Protocol):
    async def check(
        self,
        graph: ConceptGraph,
        *,
        owner_id: str | None,
        run_id: str,
        policy: CorpusAccessPolicy = CorpusAccessPolicy.TEACH,
    ) -> None:
        """Revalidate current owner/source identity; inspection alone may read pending graphs."""
        ...
