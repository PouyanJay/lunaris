from .search_provider import ISearchProvider
from .video_result import VideoResult


class SearchVideoSource:
    """The no-key video fallback: find videos via the shared ``ISearchProvider`` (P7.4).

    When no ``YOUTUBE_API_KEY`` is set, video candidates come from the same general web search as
    articles/docs — so a video query still returns candidates (the curator + trust gate vet them),
    just without the rich duration/channel signals the YouTube Data API exposes. Best-effort: a
    search failure is swallowed-and-logged by the underlying provider, surfacing as an empty list.
    """

    def __init__(self, search: ISearchProvider) -> None:
        self._search = search

    async def find(self, query: str, *, max_results: int = 5) -> list[VideoResult]:
        results = await self._search.search(query, max_results=max_results)
        return [VideoResult(url=result.url, title=result.title) for result in results]
