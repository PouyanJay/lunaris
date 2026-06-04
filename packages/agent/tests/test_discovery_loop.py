"""The discovery sub-graph (plan → search → fetch → gate → ingest → reflect).

Drives the real ``SubgraphGroundingDiscoverer`` over stub search + extraction + a shared in-memory
corpus, so the whole loop is exercised deterministically: machine-found sources are graded by the
credibility scorer, off-topic ones are dropped by the label-blind judge, blocked domains never get
fetched, every accepted source lands in the course corpus with its provenance + a streamed
``SOURCE_EVALUATED`` verdict, and the bounded reflect cycle re-queries under-covered concepts.
"""

import pytest
from lunaris_agent.harness.agent_reporter import AgentReporter
from lunaris_agent.harness.discovery import (
    DiscoveryBudget,
    StubRelevanceJudge,
    SubgraphGroundingDiscoverer,
)
from lunaris_agent.harness.draft import CourseDraft
from lunaris_grounding import (
    CorpusIngestor,
    CredibilityScorer,
    ExtractedContent,
    InMemoryCorpusStore,
    InMemorySourceAuthorityStore,
    ScholarlyRecord,
    SearchResult,
    StubContentExtractor,
    StubEmbedder,
    StubSearchProvider,
)
from lunaris_runtime.schema import (
    AcquisitionMode,
    AgentEventKind,
    BloomLevel,
    KnowledgeComponent,
    TrustTier,
)

_CLOCK = "2026-06-04T00:00:00+00:00"


def _kc(kc_id: str, label: str) -> KnowledgeComponent:
    return KnowledgeComponent(
        id=kc_id,
        label=label,
        definition=f"about {label}",
        difficulty=0.5,
        bloom_ceiling=BloomLevel.APPLY,
    )


def _draft(sink: AgentReporter, *, concepts: list[KnowledgeComponent]) -> CourseDraft:
    draft = CourseDraft(topic="Algorithms", course_id="course-x", run_id="run-x")
    draft.concepts = concepts
    draft.agent = sink
    return draft


def _discoverer(
    *,
    results: list[SearchResult],
    pages: dict[str, ExtractedContent],
    judge: object | None = None,
    scorer: CredibilityScorer | None = None,
    corpus: InMemoryCorpusStore,
    search: object | None = None,
    budget: DiscoveryBudget | None = None,
) -> SubgraphGroundingDiscoverer:
    return SubgraphGroundingDiscoverer(
        search or StubSearchProvider(results),
        StubContentExtractor(pages),
        scorer or CredibilityScorer(InMemorySourceAuthorityStore()),
        judge or StubRelevanceJudge(),
        CorpusIngestor(StubEmbedder(), corpus),
        budget=budget,
        clock=lambda: _CLOCK,
    )


async def test_grades_and_ingests_a_relevant_open_source(agent_sink) -> None:
    # Arrange — one concept, one on-topic open-web page.
    url = "https://study.example/dijkstra"
    corpus = InMemoryCorpusStore()
    discoverer = _discoverer(
        results=[SearchResult(url=url, title="Dijkstra", snippet="…")],
        pages={url: ExtractedContent(url=url, text="Dijkstra's algorithm finds shortest paths.")},
        corpus=corpus,
        scorer=CredibilityScorer(InMemorySourceAuthorityStore()),
    )
    draft = _draft(
        AgentReporter("run-x", agent_sink), concepts=[_kc("dijkstra", "Dijkstra's algorithm")]
    )

    # Act
    report = await discoverer.discover(draft)

    # Assert — the source is ingested for its concept, graded (OPEN + a credibility), marked AUTO.
    assert report.sources_accepted == 1
    assert report.chunks_ingested > 0
    assert report.covered_kcs == ("dijkstra",)
    (summary,) = await corpus.list_sources_for_course("course-x")
    assert summary.acquisition_mode is AcquisitionMode.AUTO
    assert summary.trust_tier is TrustTier.OPEN  # an unknown open-web host, graded by the scorer
    assert summary.credibility is not None
    assert summary.fetched_at == _CLOCK
    # The vetting verdict streamed to the canvas, carrying the graded provenance.
    (evaluated,) = [e for e in agent_sink.events if e.kind is AgentEventKind.SOURCE_EVALUATED]
    assert evaluated.source is not None
    assert evaluated.source.accepted is True
    assert evaluated.source.domain == "study.example"
    assert evaluated.source.credibility is not None


async def test_the_judge_drops_an_off_topic_source(agent_sink) -> None:
    # Arrange — a page that ranks for the query but does not teach the concept.
    url = "https://blog.example/pasta"
    corpus = InMemoryCorpusStore()
    discoverer = _discoverer(
        results=[SearchResult(url=url, title="Pasta", snippet="…")],
        pages={url: ExtractedContent(url=url, text="A recipe for cooking pasta al dente.")},
        corpus=corpus,
    )
    draft = _draft(
        AgentReporter("run-x", agent_sink), concepts=[_kc("dijkstra", "Dijkstra's algorithm")]
    )

    # Act
    report = await discoverer.discover(draft)

    # Assert — nothing ingested, and the rejection is surfaced (not silently dropped).
    assert report.sources_accepted == 0
    assert await corpus.list_sources_for_course("course-x") == []
    (evaluated,) = [e for e in agent_sink.events if e.kind is AgentEventKind.SOURCE_EVALUATED]
    assert evaluated.source is not None and evaluated.source.accepted is False


async def test_a_blocked_domain_is_never_fetched_or_ingested(agent_sink) -> None:
    # Arrange — a search hit on a cloud metadata IP (an SSRF target classify_domain blocks).
    blocked = "http://169.254.169.254/latest/meta-data"
    corpus = InMemoryCorpusStore()
    discoverer = _discoverer(
        results=[SearchResult(url=blocked, title="x", snippet="…")],
        pages={blocked: ExtractedContent(url=blocked, text="Dijkstra's algorithm.")},
        corpus=corpus,
    )
    draft = _draft(
        AgentReporter("run-x", agent_sink), concepts=[_kc("dijkstra", "Dijkstra's algorithm")]
    )

    # Act
    report = await discoverer.discover(draft)

    # Assert — dropped before any fetch; nothing ingested.
    assert report.sources_accepted == 0
    assert await corpus.list_sources_for_course("course-x") == []
    assert not [e for e in agent_sink.events if e.kind is AgentEventKind.SOURCE_EVALUATED]


class _RecordingRegistry:
    """A scholarly registry that confirms a peer-reviewed record for every URL (test seam)."""

    async def lookup(self, url: str) -> ScholarlyRecord | None:
        return ScholarlyRecord(venue="Journal of Algorithms", doi="10.0/x")


async def test_a_registry_confirmed_paper_on_an_unknown_host_is_graded_reputable(
    agent_sink,
) -> None:
    # Arrange — an unknown open-web host the scholarly registry confirms hosts a real paper.
    url = "https://unknown-journal.example/dijkstra"
    corpus = InMemoryCorpusStore()
    scorer = CredibilityScorer(InMemorySourceAuthorityStore(), registry=_RecordingRegistry())
    discoverer = _discoverer(
        results=[SearchResult(url=url, title="Dijkstra", snippet="…")],
        pages={url: ExtractedContent(url=url, text="Dijkstra's algorithm finds shortest paths.")},
        corpus=corpus,
        scorer=scorer,
    )
    draft = _draft(
        AgentReporter("run-x", agent_sink), concepts=[_kc("dijkstra", "Dijkstra's algorithm")]
    )

    # Act
    await discoverer.discover(draft)

    # Assert — the machine-found paper is floored to REPUTABLE, not left open web (the headline).
    (summary,) = await corpus.list_sources_for_course("course-x")
    assert summary.trust_tier is TrustTier.REPUTABLE
    assert summary.credibility == pytest.approx(0.75)


async def test_empty_search_ingests_nothing_without_error(agent_sink) -> None:
    # Arrange — search returns no hits (the honest no-results path).
    corpus = InMemoryCorpusStore()
    discoverer = _discoverer(results=[], pages={}, corpus=corpus)
    draft = _draft(
        AgentReporter("run-x", agent_sink), concepts=[_kc("dijkstra", "Dijkstra's algorithm")]
    )

    # Act
    report = await discoverer.discover(draft)

    # Assert — a clean empty pass.
    assert report.sources_accepted == 0
    assert report.chunks_ingested == 0
    assert await corpus.list_sources_for_course("course-x") == []


class _RoutingSearch:
    """A search provider returning results by which concept label is in the query; counts calls."""

    def __init__(self, by_token: dict[str, list[SearchResult]]) -> None:
        self._by_token = by_token
        self.queries: list[str] = []

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        self.queries.append(query)
        for token, results in self._by_token.items():
            if token in query:
                return results[:max_results]
        return []


def _page(url: str, label: str) -> ExtractedContent:
    """A page whose text mentions the concept label, so the token-overlap stub judge accepts it."""
    return ExtractedContent(url=url, text=f"A thorough explanation of {label}.")


async def test_a_concept_with_two_domains_is_covered_in_one_round(agent_sink) -> None:
    # Arrange — one concept, two hits on two distinct domains (cross-source coverage in one pass).
    results = [
        SearchResult(url="https://d1.example/alpha", title="Alpha", snippet="…"),
        SearchResult(url="https://d2.example/alpha", title="Alpha", snippet="…"),
    ]
    search = _RoutingSearch({"Alpha": results})
    corpus = InMemoryCorpusStore()
    discoverer = _discoverer(
        results=[],
        search=search,
        pages={r.url: _page(r.url, "Alpha") for r in results},
        corpus=corpus,
        budget=DiscoveryBudget(searches_per_round=2, fetches_per_round=4, max_rounds=3),
    )
    draft = _draft(AgentReporter("run-x", agent_sink), concepts=[_kc("alpha", "Alpha")])

    # Act
    report = await discoverer.discover(draft)

    # Assert — covered with two domains; reflect ends immediately (one planning round, no re-query).
    assert report.sources_accepted == 2
    assert report.covered_kcs == ("alpha",)
    assert len(search.queries) == 1


async def test_reflect_re_queries_a_concept_the_first_round_skipped(agent_sink) -> None:
    # Arrange — two concepts but one search per round, so round 1 grounds Alpha and leaves Beta;
    # the reflect cycle must come back and ground Beta in round 2.
    alpha = [
        SearchResult(url="https://d1.example/alpha", title="Alpha", snippet="…"),
        SearchResult(url="https://d2.example/alpha", title="Alpha", snippet="…"),
    ]
    beta = [
        SearchResult(url="https://d3.example/beta", title="Beta", snippet="…"),
        SearchResult(url="https://d4.example/beta", title="Beta", snippet="…"),
    ]
    search = _RoutingSearch({"Alpha": alpha, "Beta": beta})
    pages = {r.url: _page(r.url, "Alpha") for r in alpha} | {
        r.url: _page(r.url, "Beta") for r in beta
    }
    corpus = InMemoryCorpusStore()
    discoverer = _discoverer(
        results=[],
        search=search,
        pages=pages,
        corpus=corpus,
        budget=DiscoveryBudget(searches_per_round=1, fetches_per_round=4, max_rounds=2),
    )
    draft = _draft(
        AgentReporter("run-x", agent_sink), concepts=[_kc("alpha", "Alpha"), _kc("beta", "Beta")]
    )

    # Act
    report = await discoverer.discover(draft)

    # Assert — both concepts grounded, across two reflect rounds (one query each). Alpha is queried
    # first because the concepts share a difficulty, so the hardest-first sort is a stable no-op.
    assert report.covered_kcs == ("alpha", "beta")
    assert report.sources_accepted == 4
    assert search.queries == ["Alpha Algorithms", "Beta Algorithms"]


async def test_reflect_stops_when_a_round_adds_no_new_evidence(agent_sink) -> None:
    # Arrange — a concept reachable on only ONE domain, so it can never hit the two-domain bar.
    # Round 1 ingests it; round 2 re-queries, finds only the same URL, and the no-progress guard
    # ends the loop before the round ceiling (no infinite re-querying of an uncoverable concept).
    only = [SearchResult(url="https://d1.example/alpha", title="Alpha", snippet="…")]
    search = _RoutingSearch({"Alpha": only})
    corpus = InMemoryCorpusStore()
    discoverer = _discoverer(
        results=[],
        search=search,
        pages={only[0].url: _page(only[0].url, "Alpha")},
        corpus=corpus,
        budget=DiscoveryBudget(searches_per_round=2, fetches_per_round=4, max_rounds=5),
    )
    draft = _draft(AgentReporter("run-x", agent_sink), concepts=[_kc("alpha", "Alpha")])

    # Act
    report = await discoverer.discover(draft)

    # Assert — the one reachable source landed once (not duplicated), and the loop stopped after the
    # re-query found nothing new — far short of the 5-round ceiling.
    assert report.sources_accepted == 1
    assert len(await corpus.list_sources_for_course("course-x")) == 1
    assert len(search.queries) == 2


class _OneDomainNewPathSearch:
    """Returns a fresh URL on the SAME domain every call: each round adds a new source (so the
    no-progress guard never fires) but the concept never reaches two domains (so coverage never
    completes) — leaving the max-round ceiling as the only possible stop."""

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        self.calls += 1
        return [SearchResult(url=f"https://one.example/alpha/{self.calls}", title="Alpha")]


class _AlphaExtractor:
    """Extracts an on-topic page for any URL (the fetch boundary for the ceiling test)."""

    async def extract(self, url: str) -> ExtractedContent:
        return _page(url, "Alpha")


async def test_reflect_stops_at_the_round_ceiling(agent_sink) -> None:
    # Arrange — every round finds a new source (progress) but all on one domain (never cross-source
    # covered), so neither the no-progress guard nor the coverage stop fires; only the ceiling can.
    search = _OneDomainNewPathSearch()
    corpus = InMemoryCorpusStore()
    discoverer = SubgraphGroundingDiscoverer(
        search,
        _AlphaExtractor(),
        CredibilityScorer(InMemorySourceAuthorityStore()),
        StubRelevanceJudge(),
        CorpusIngestor(StubEmbedder(), corpus),
        budget=DiscoveryBudget(searches_per_round=1, fetches_per_round=4, max_rounds=2),
        clock=lambda: _CLOCK,
    )
    draft = _draft(AgentReporter("run-x", agent_sink), concepts=[_kc("alpha", "Alpha")])

    # Act
    report = await discoverer.discover(draft)

    # Assert — it ran the full two rounds (progress each round) then halted at the ceiling, with two
    # same-domain sources ingested — proving the ceiling stop independently of the other two exits.
    assert search.calls == 2
    assert report.sources_accepted == 2


def test_a_discovery_budget_must_have_at_least_one_round() -> None:
    # Arrange / Act / Assert — a zero-round budget is a misconfiguration, rejected at construction.
    with pytest.raises(ValueError, match="at least one round"):
        DiscoveryBudget(max_rounds=0)
