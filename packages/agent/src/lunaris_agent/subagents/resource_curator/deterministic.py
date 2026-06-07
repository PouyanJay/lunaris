from lunaris_runtime.schema import CourseBrief, Modality, Module

from .query import build_resource_queries
from .search_query import SearchQuery


class DeterministicQueryTranslator:
    """The model-free query planner — today's per-kind templates, wrapped as the translator seam.

    Plans one query per sourced kind from the module's competency (see ``build_resource_queries``).
    It ignores ``modality``/``feedback`` (no shaping, no broaden) — that intelligence is the LLM
    translator's job (CQ Phase 2 T1); this is the deterministic FALLBACK the curator uses when the
    LLM call fails or no key is set, and the default when none is injected. No model, no network.
    """

    async def translate(
        self,
        module: Module,
        brief: CourseBrief | None = None,
        *,
        modality: Modality | None = None,
        feedback: str | None = None,
    ) -> list[SearchQuery]:
        return [
            SearchQuery(kind=kind, query=query)
            for kind, query in build_resource_queries(module, brief)
        ]
