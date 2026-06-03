"""P7.2-T3 — the Tavily-backed ISearchProvider, tested offline via an injected client.

The provider maps Tavily's response into SearchResults and is best-effort: a transport error (or a
missing key) yields an empty list rather than an exception, so a flaky search never breaks a build.
The real Tavily SDK is only imported lazily when no client is injected, so these tests never touch
the network.
"""

import pytest
from lunaris_grounding import TavilySearchProvider


class _FakeTavilyClient:
    """Records its calls and returns a canned response (stands in for the sync TavilyClient)."""

    def __init__(self, response: object) -> None:
        self._response = response
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, *, max_results: int = 5) -> object:
        self.calls.append((query, max_results))
        return self._response


class _RaisingTavilyClient:
    """A Tavily client that always raises — to prove the provider absorbs a flaky backend."""

    def search(self, query: str, *, max_results: int = 5) -> object:
        raise RuntimeError("tavily is down")


async def test_maps_tavily_results_into_search_results() -> None:
    # Arrange
    client = _FakeTavilyClient(
        {
            "results": [
                {"url": "https://ircc.canada.ca/clb", "title": "CLB 10", "content": "about CLB 10"},
                {"url": "https://uni.edu/clb", "title": "Guide", "content": "more"},
            ]
        }
    )
    provider = TavilySearchProvider(client=client)

    # Act
    results = await provider.search("CLB 10 competency descriptors", max_results=2)

    # Assert — url/title/snippet mapped for every hit, and the query + cap reached Tavily.
    assert [r.url for r in results] == ["https://ircc.canada.ca/clb", "https://uni.edu/clb"]
    assert (results[0].title, results[0].snippet) == ("CLB 10", "about CLB 10")
    assert (results[1].title, results[1].snippet) == ("Guide", "more")
    assert client.calls == [("CLB 10 competency descriptors", 2)]


async def test_skips_results_without_a_url() -> None:
    # Arrange — a malformed hit with no URL is unusable and must be dropped, not crash the mapping.
    client = _FakeTavilyClient({"results": [{"title": "no url"}, {"url": "https://ok.edu"}]})
    provider = TavilySearchProvider(client=client)

    # Act / Assert
    results = await provider.search("q")
    assert [r.url for r in results] == ["https://ok.edu"]


async def test_returns_empty_when_the_client_raises() -> None:
    # Arrange — a flaky backend; best-effort degradation must absorb it.
    provider = TavilySearchProvider(client=_RaisingTavilyClient())

    # Act / Assert
    assert await provider.search("q") == []


async def test_degrades_to_empty_when_the_search_key_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — no key and no injected client; the missing-key error is absorbed (the composition
    # key-gates the real provider, so this path only happens if the key vanishes mid-run).
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    provider = TavilySearchProvider()

    # Act / Assert — no results, build unbroken.
    assert await provider.search("q") == []
