"""P6.3-T2: the discovery sub-graph (plan → search → fetch → gate → ingest).

Drives the real ``SubgraphGroundingDiscoverer`` over stub search + extraction + a shared in-memory
corpus, so the whole loop is exercised deterministically: machine-found sources are graded by the
credibility scorer, off-topic ones are dropped by the label-blind judge, blocked domains never get
fetched, and every accepted source lands in the course corpus with its provenance + a streamed
``SOURCE_EVALUATED`` verdict.
"""

import pytest
from lunaris_agent.harness.agent_reporter import AgentReporter
from lunaris_agent.harness.discovery import StubRelevanceJudge, SubgraphGroundingDiscoverer
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
) -> SubgraphGroundingDiscoverer:
    return SubgraphGroundingDiscoverer(
        StubSearchProvider(results),
        StubContentExtractor(pages),
        scorer or CredibilityScorer(InMemorySourceAuthorityStore()),
        judge or StubRelevanceJudge(),
        CorpusIngestor(StubEmbedder(), corpus),
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
