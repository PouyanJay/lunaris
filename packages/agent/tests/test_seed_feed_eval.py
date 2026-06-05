"""P6.4 (T4) — the SEED-feed grounded-build eval (live, key-gated).

The end-to-end proof that the near-free seed feed fills a real corpus with usable, graded evidence:
against real search (Tavily) + fetch/extract (Trafilatura) + a real embedder + a real Supabase
pgvector corpus + a real independent Claude assessor, the standard-research stage's already-fetched
pages, seeded through ``GroundingSeeder``, must ingest >=1 graded source AND let a TRUE claim about
the topic reach SUPPORTED — with no second fetch beyond what research already paid for. The
deterministic ``test_seed_poisoning`` / ``test_hybrid_corpus`` suites prove the wiring + the floor
offline; this proves the whole path works on live infrastructure. Deselected by default:

    uv run --env-file .env pytest -m eval -q

Gated on ``SEARCH_API_KEY`` + the D2 corpus creds + an Anthropic key; skips when any is absent. The
ingested rows are best-effort cleaned up in teardown so a live corpus isn't polluted by the probe.
"""

import os

import pytest
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.seeding import GroundingSeeder
from lunaris_agent.subagents.standard_researcher import ClaudeStandardResearcher
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
from lunaris_runtime.schema import Claim, CourseBrief, RiskTier, VerifierStatus

pytestmark = pytest.mark.eval

_RESEARCHER_MODEL = "claude-haiku-4-5-20251001"
_ASSESSOR_MODEL = "claude-opus-4-8"
_HAS_CORPUS = bool(
    os.getenv("SUPABASE_URL")
    and os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    and os.getenv("EMBEDDINGS_API_KEY")
)
_HAS_SEARCH = bool(os.getenv("SEARCH_API_KEY"))
_HAS_ANTHROPIC = bool(os.getenv("ANTHROPIC_API_KEY"))
_COURSE = "seed-feed-eval"
# A goal whose authoritative sources the research stage will fetch — those pages become the seeds.
_RESEARCH_TARGET = CourseBrief(
    subject="Dijkstra's shortest-path algorithm",
    goal="Understand how Dijkstra's algorithm finds shortest paths",
)
# A TRUE, well-documented claim the seeded research pages should corroborate.
_TRUE_CLAIM = "Dijkstra's algorithm finds shortest paths from a single source vertex"


@pytest.mark.skipif(not _HAS_SEARCH, reason="SEARCH_API_KEY not set")
@pytest.mark.skipif(not _HAS_CORPUS, reason="Supabase/embeddings creds not set")
@pytest.mark.skipif(not _HAS_ANTHROPIC, reason="Anthropic key not set")
async def test_seeding_grounds_a_true_claim_against_a_live_corpus() -> None:
    # Arrange — the real research stage fetches authoritative pages for the goal; its fetched
    # text is seeded into the real corpus, graded by the same scorer + registry as discovery.
    researcher = ClaudeStandardResearcher(
        _RESEARCHER_MODEL, TavilySearchProvider(), TrafilaturaContentExtractor()
    )
    outcome = await researcher.research(_RESEARCH_TARGET)
    assert outcome.seeds, "research fetched no pages to seed"

    store = SupabaseCorpusStore()
    seeder = GroundingSeeder(
        CorpusIngestor(
            VoyageEmbedder(),
            store,
            scorer=CredibilityScorer(
                InMemorySourceAuthorityStore(),
                registry=OpenAlexScholarlyRegistry(mailto=os.getenv("OPENALEX_EMAIL")),
            ),
        )
    )
    draft = CourseDraft(topic="Algorithms", course_id=_COURSE, run_id="seed-eval")
    draft.research_seeds = list(outcome.seeds)

    try:
        # Act — seed the corpus from research, then verify a TRUE claim against the filled corpus.
        report = await seeder.seed(draft)
        assert report.sources_seeded >= 1, "seeding ingested no source"
        summaries = await store.list_sources_for_course(_COURSE)
        assert summaries and all(s.credibility is not None for s in summaries), "seeds not graded"

        verifier = Verifier(
            PgVectorRetriever(VoyageEmbedder(), store), ClaudeSupportAssessor(_ASSESSOR_MODEL)
        )
        claim = Claim(text=_TRUE_CLAIM)
        await verifier.verify([claim], risk_tier=RiskTier.LOW, course_id=_COURSE)

        # Assert — a true claim is grounded by the seeded, graded evidence (not vacuously cut
        # against an empty corpus). LOW risk: one relevant source the build already read suffices.
        assert claim.verifier_status is VerifierStatus.SUPPORTED
        assert claim.supported_by is not None
    finally:
        # Best-effort cleanup so the probe's rows don't linger in the shared live corpus.
        for summary in await store.list_sources_for_course(_COURSE):
            await store.delete_source(summary.source_id)
