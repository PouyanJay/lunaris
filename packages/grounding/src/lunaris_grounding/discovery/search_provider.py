from typing import Protocol

from .search_result import SearchResult


class ISearchProvider(Protocol):
    """Runs a web search and returns ranked candidate results (P7.2 / P6 shared discovery layer).

    The single search dependency for the whole product: P7 researches to *design* the curriculum and
    P6 researches to *ground claims*, both behind this Protocol so the backend (Tavily, Brave, …)
    stays swappable and the no-key path uses a deterministic stub. Implementations must be
    best-effort — a transport failure surfaces as an empty list, never an exception that aborts a
    build.
    """

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]: ...
