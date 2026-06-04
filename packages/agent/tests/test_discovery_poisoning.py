"""P6.3 (T6) — the headline "auto-discovery didn't invert the moat" gate, deterministic.

The trap (plan §1): the discovery sub-graph fetches a topically-relevant page that asserts a WRONG
claim; the relevance judge (rightly) keeps it as on-topic; a naive assessor would rubber-stamp it.
These tests run the REAL discovery path (search → fetch → gate → ingest) into a shared corpus, then
verify against that corpus — proving the P6.2 trust floor still holds on MACHINE-FOUND evidence:

1. A lone open-web source the discoverer ingests cannot ground a HIGH-risk claim (the worst case:
   StubSupportAssessor always SUPPORTS, so only the floor can cut it).
2. The same machine-found evidence, corroborated across two independent domains, clears the floor —
   discovery that achieves cross-source coverage *does* ground claims.

Both run on every commit (no model, no network); the live, key-gated build proof is in
``test_auto_discovery_eval.py``.
"""

from lunaris_agent.harness.agent_reporter import AgentReporter
from lunaris_agent.harness.discovery import StubRelevanceJudge, SubgraphGroundingDiscoverer
from lunaris_agent.harness.draft import CourseDraft
from lunaris_grounding import (
    CorpusIngestor,
    CredibilityScorer,
    ExtractedContent,
    InMemoryCorpusStore,
    InMemorySourceAuthorityStore,
    PgVectorRetriever,
    SearchResult,
    StubContentExtractor,
    StubEmbedder,
    StubSupportAssessor,
    Verifier,
)
from lunaris_runtime.schema import (
    BloomLevel,
    Claim,
    KnowledgeComponent,
    RiskTier,
    TrustTier,
    VerifierStatus,
)

_DIM = 96
_COURSE = "poison-course"
# Wrong but topically-relevant (the classic probe): Dijkstra's algorithm does NOT handle negative
# edge weights. The page mentions "Dijkstra", so the topical relevance judge keeps it — only the
# verifier's trust floor stops it from grounding the claim.
_WRONG_CLAIM = "Dijkstra's algorithm works correctly with negative edge weights"
_KC = KnowledgeComponent(
    id="dijkstra",
    label="Dijkstra's algorithm",
    definition="shortest paths",
    difficulty=0.5,
    bloom_ceiling=BloomLevel.APPLY,
)


def _draft() -> CourseDraft:
    draft = CourseDraft(topic="Algorithms", course_id=_COURSE, run_id="run-x")
    draft.concepts = [_KC]
    draft.agent = AgentReporter("run-x")
    return draft


def _discoverer(
    corpus: InMemoryCorpusStore, results: list[SearchResult], pages: dict[str, ExtractedContent]
) -> SubgraphGroundingDiscoverer:
    return SubgraphGroundingDiscoverer(
        _Search(results),
        StubContentExtractor(pages),
        CredibilityScorer(InMemorySourceAuthorityStore()),
        StubRelevanceJudge(),
        CorpusIngestor(StubEmbedder(dim=_DIM), corpus),
        clock=lambda: "2026-06-04T00:00:00+00:00",
    )


class _Search:
    """Returns the same canned hits for any query (the KC is the only concept here)."""

    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return self._results[:max_results]


def _verifier(corpus: InMemoryCorpusStore) -> Verifier:
    # min_score=0.0 so retrieval never filters on the stub embedder — the floor, not relevance, is
    # what's under test. StubSupportAssessor always SUPPORTS, so a CUT can only come from the floor.
    return Verifier(
        PgVectorRetriever(StubEmbedder(dim=_DIM), corpus, min_score=0.0), StubSupportAssessor()
    )


async def test_a_machine_found_open_source_cannot_ground_a_high_risk_claim() -> None:
    # Arrange — discovery finds ONE topical-but-wrong SEO page and ingests it (scored → OPEN).
    corpus = InMemoryCorpusStore()
    url = "https://seo-slop.example/dijkstra-negative-weights"
    discoverer = _discoverer(
        corpus,
        [SearchResult(url=url, title="Dijkstra", snippet="…")],
        {url: ExtractedContent(url=url, text=f"{_WRONG_CLAIM}. Dijkstra, repeated for SEO. " * 3)},
    )
    report = await discoverer.discover(_draft())
    assert report.sources_accepted == 1  # the judge kept it (it IS on-topic — that's the trap)
    claim = Claim(text=_WRONG_CLAIM)

    # Act — verify the wrong claim at HIGH risk against the discovered corpus.
    await _verifier(corpus).verify([claim], risk_tier=RiskTier.HIGH, course_id=_COURSE)

    # Assert — the moat holds on machine-found evidence: a lone OPEN source can't ground a
    # high-stakes claim, even though the assessor supported it — auto-discovery didn't invert it.
    assert claim.verifier_status is VerifierStatus.CUT
    (summary,) = await corpus.list_sources_for_course(_COURSE)
    assert summary.trust_tier is TrustTier.OPEN  # down-ranked, as the floor expects


async def test_machine_found_evidence_across_two_domains_clears_the_high_risk_floor() -> None:
    # Arrange — discovery finds the claim on TWO independent domains (the cross-source coverage the
    # reflect loop chases). Distinct bodies so both chunks are retrieved, not deduped into one.
    corpus = InMemoryCorpusStore()
    claim_text = "binary search runs in logarithmic time by halving the sorted array"
    one, two = "https://one.example/bs", "https://two.example/bs"
    discoverer = _discoverer(
        corpus,
        [
            SearchResult(url=one, title="x", snippet="…"),
            SearchResult(url=two, title="y", snippet="…"),
        ],
        {
            one: ExtractedContent(
                url=one,
                text="Binary search halves the sorted array — logarithmic time, source one.",
            ),
            two: ExtractedContent(
                url=two, text="Logarithmic time: binary search halves the sorted array, source two."
            ),
        },
    )
    draft = _draft()
    draft.concepts = [
        KnowledgeComponent(
            id="bs",
            label="binary search",
            definition="halving search",
            difficulty=0.5,
            bloom_ceiling=BloomLevel.APPLY,
        )
    ]
    report = await discoverer.discover(draft)
    # Both kept, so a SUPPORTED verdict means the floor cleared on evidence, not an empty corpus.
    assert report.sources_accepted == 2
    claim = Claim(text=claim_text)

    # Act
    await _verifier(corpus).verify([claim], risk_tier=RiskTier.HIGH, course_id=_COURSE)

    # Assert — corroboration across two discovered domains clears the floor.
    assert claim.verifier_status is VerifierStatus.SUPPORTED
