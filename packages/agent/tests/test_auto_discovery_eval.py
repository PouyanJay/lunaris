"""P6.3 (T6) — the auto-discovery grounded-build eval (live, key-gated).

The end-to-end proof that the discovery sub-graph fills a real corpus with usable, graded evidence:
against real search (Tavily) + fetch/extract (Trafilatura) + a real embedder + a real Supabase
pgvector corpus + a real independent Claude assessor, discovering grounding for a well-known concept
must ingest >=1 graded source AND let a TRUE claim about it reach SUPPORTED. The deterministic
``test_discovery_loop`` / ``test_discovery_poisoning`` suites prove the wiring + the floor offline;
this proves the whole path works on live infrastructure. Deselected by default:

    uv run --env-file .env pytest -m eval -q

Gated on ``SEARCH_API_KEY`` + the D2 corpus creds + an Anthropic key; skips when any is absent. The
ingested rows are best-effort cleaned up in teardown so a live corpus isn't polluted by the probe.
"""

import os

import pytest
from lunaris_agent.harness.agent_reporter import AgentReporter
from lunaris_agent.harness.discovery import ClaudeRelevanceJudge, SubgraphGroundingDiscoverer
from lunaris_agent.harness.draft import CourseDraft
from lunaris_grounding import (
    ClaudeSupportAssessor,
    CorpusIngestor,
    CredibilityScorer,
    InMemorySourceAuthorityStore,
    OpenAlexScholarlyRegistry,
    PgVectorRetriever,
    SupabaseCorpusStore,
    TavilySearchProvider,
    TrafilaturaContentExtractor,
    Verifier,
    VoyageEmbedder,
)
from lunaris_runtime.schema import BloomLevel, Claim, KnowledgeComponent, RiskTier, VerifierStatus

pytestmark = pytest.mark.eval

_WORKER = "claude-haiku-4-5-20251001"
_STRONG = "claude-opus-4-8"
_HAS_CORPUS = bool(
    os.getenv("SUPABASE_URL")
    and os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    and os.getenv("EMBEDDINGS_API_KEY")
)
_HAS_SEARCH = bool(os.getenv("SEARCH_API_KEY"))
_HAS_ANTHROPIC = bool(os.getenv("ANTHROPIC_API_KEY"))
_COURSE = "auto-discovery-eval"
_KC = KnowledgeComponent(
    id="dijkstra",
    label="Dijkstra's algorithm",
    definition="finds shortest paths from a source vertex in a non-negative weighted graph",
    difficulty=0.5,
    bloom_ceiling=BloomLevel.APPLY,
)
# A TRUE, well-documented claim the discovered sources should corroborate.
_TRUE_CLAIM = "Dijkstra's algorithm finds shortest paths from a single source vertex"


@pytest.mark.skipif(not _HAS_SEARCH, reason="SEARCH_API_KEY not set")
@pytest.mark.skipif(not _HAS_CORPUS, reason="Supabase/embeddings creds not set")
@pytest.mark.skipif(not _HAS_ANTHROPIC, reason="Anthropic key not set")
async def test_discovery_grounds_a_true_claim_against_a_live_corpus() -> None:
    # Arrange — the live discoverer over the real search/fetch/score stack, writing the real corpus.
    store = SupabaseCorpusStore()
    discoverer = SubgraphGroundingDiscoverer(
        TavilySearchProvider(),
        TrafilaturaContentExtractor(),
        CredibilityScorer(
            InMemorySourceAuthorityStore(),
            registry=OpenAlexScholarlyRegistry(mailto=os.getenv("OPENALEX_EMAIL")),
        ),
        ClaudeRelevanceJudge(_WORKER),
        CorpusIngestor(VoyageEmbedder(), store),
    )
    draft = CourseDraft(topic="Algorithms", course_id=_COURSE, run_id="auto-eval")
    draft.concepts = [_KC]
    draft.agent = AgentReporter("auto-eval")

    try:
        # Act — discover grounding, then verify a TRUE claim against the freshly-filled corpus.
        report = await discoverer.discover(draft)
        assert report.sources_accepted >= 1, "discovery ingested no graded source"
        summaries = await store.list_sources_for_course(_COURSE)
        assert summaries and all(s.trust_tier is not None for s in summaries), "sources not graded"

        verifier = Verifier(
            PgVectorRetriever(VoyageEmbedder(), store), ClaudeSupportAssessor(_STRONG)
        )
        claim = Claim(text=_TRUE_CLAIM)
        await verifier.verify([claim], risk_tier=RiskTier.LOW, course_id=_COURSE)

        # Assert — a true claim is grounded by the machine-discovered, graded evidence (not
        # vacuously cut against an empty corpus). LOW risk: one relevant open-web source suffices.
        assert claim.verifier_status is VerifierStatus.SUPPORTED
        assert claim.supported_by is not None
    finally:
        # Best-effort cleanup so the probe's rows don't linger in the shared live corpus.
        for summary in await store.list_sources_for_course(_COURSE):
            await store.delete_source(summary.source_id)
