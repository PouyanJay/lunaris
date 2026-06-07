from typing import Protocol

from lunaris_runtime.schema import CourseBrief, Modality, Module

from .search_query import SearchQuery


class IQueryTranslator(Protocol):
    """Plans the resource searches for one module's competency (CQ Phase 2).

    The seam in front of the search API: it rewrites the competency into the domain's real search
    vernacular and shapes the queries from the course ``goal_type`` (on the brief) + the module's
    representative ``modality`` — so a receptive competency seeks INPUT material, an exam goal uses
    the real exam name + task, etc. — instead of the old ``"{competency} video tutorial"`` template
    that returned junk on abstract competencies. ``feedback`` lets the curator ask for a broader
    retry when a module came up empty. Swappable: a live LLM translator vs the deterministic one.
    """

    async def translate(
        self,
        module: Module,
        brief: CourseBrief | None = None,
        *,
        modality: Modality | None = None,
        feedback: str | None = None,
    ) -> list[SearchQuery]: ...
