from collections.abc import Sequence

from .search_result import SearchResult


class StubSearchProvider:
    """A deterministic search provider for the no-key path + tests.

    Returns a preconfigured list of results for every query (capped at ``max_results``), or an empty
    list when unconfigured — so the research stage degrades honestly to ``UNAVAILABLE`` offline,
    exactly as a real provider returning nothing would. Tests inject canned results to drive the
    downstream fetch + distillation without touching the network.
    """

    def __init__(self, results: Sequence[SearchResult] | None = None) -> None:
        self._results = list(results or [])

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return self._results[:max_results]
