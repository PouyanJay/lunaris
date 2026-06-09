"""The keyless search fallback: DuckDuckGo (no API key) maps hits to SearchResult and, like Tavily,
is best-effort — any failure returns [] rather than breaking a build."""

from lunaris_grounding import DuckDuckGoSearchProvider, SearchResult


class _FakeDDGS:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def text(self, query: str, *, max_results: int) -> list[dict[str, str]]:
        return self._rows


async def test_maps_duckduckgo_hits_to_search_results() -> None:
    client = _FakeDDGS(
        [
            {"href": "https://example.edu/a", "title": "Binary search", "body": "halves the array"},
            {"href": "", "title": "no url", "body": "dropped"},  # url-less hit is unfetchable
        ]
    )

    results = await DuckDuckGoSearchProvider(client=client).search("binary search", max_results=5)

    assert results == [
        SearchResult(url="https://example.edu/a", title="Binary search", snippet="halves the array")
    ]


async def test_search_is_best_effort_and_returns_empty_on_failure() -> None:
    class _Boom:
        def text(self, *args: object, **kwargs: object) -> list[dict[str, str]]:
            raise RuntimeError("duckduckgo unavailable")

    assert await DuckDuckGoSearchProvider(client=_Boom()).search("x") == []
