"""Cost-metering coverage for the grounding paid seams (course-cost-metering, T5).

Embeddings (Voyage) and web search (Tavily) run inside the main build's cost scope, so metering is
just a ``record_cost`` at each adapter. These drive the real adapters via injected fake clients
(offline) inside a ``cost_scope`` and assert the recorded provider / unit / pocket.
"""

import pytest
from lunaris_grounding import TavilySearchProvider
from lunaris_grounding.embeddings.voyage import VoyageEmbedder
from lunaris_runtime.metering import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostPocket, CostProvider, CostSubjectType


def _scope() -> CostScope:
    return CostScope(
        run_id="r",
        subject_type=CostSubjectType.COURSE,
        subject_id="c",
        price_book=PriceBook.current(),
    )


class _FakeVoyageClient:
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class _FakeTavilyClient:
    def search(self, query: str, *, max_results: int = 5) -> dict:
        return {"results": [{"url": "http://x", "title": "t", "content": "c"}]}


async def test_voyage_embed_records_token_cost() -> None:
    # Arrange — 400 chars ~= 100 tokens at the 4-chars/token approximation.
    embedder = VoyageEmbedder()
    embedder._client = _FakeVoyageClient()  # inject the lazy client (offline)
    scope = _scope()

    # Act
    with cost_scope(scope):
        await embedder.embed(["a" * 400])

    # Assert — one Voyage embeddings cost, priced on the approximate input-token count.
    entry = scope.entries[0]
    assert entry.provider is CostProvider.VOYAGE
    assert entry.component == "embeddings"
    assert entry.usage == {"input_tokens": pytest.approx(100.0)}
    assert entry.amount == pytest.approx(100.0 * 0.06 / 1_000_000)
    # No tenant key in scope → platform pocket.
    assert entry.pocket is CostPocket.PLATFORM


async def test_tavily_search_records_one_search() -> None:
    provider = TavilySearchProvider(client=_FakeTavilyClient())
    scope = _scope()
    with cost_scope(scope):
        results = await provider.search("graphs")
    assert results  # the fake returned a hit
    entry = scope.entries[0]
    assert entry.provider is CostProvider.TAVILY
    assert entry.component == "search"
    assert entry.usage == {"search": 1}
    assert entry.amount == pytest.approx(0.008)


class _FailingTavilyClient:
    def search(self, query: str, *, max_results: int = 5) -> dict:
        raise RuntimeError("tavily down")


async def test_failed_search_records_no_cost() -> None:
    # A failed search returns [] and cost nothing — it must not record a billable request.
    provider = TavilySearchProvider(client=_FailingTavilyClient())
    scope = _scope()
    with cost_scope(scope):
        results = await provider.search("graphs")
    assert results == []
    assert scope.entries == []
