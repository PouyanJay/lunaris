"""P6.4 (T1) — the "seeding the corpus didn't invert the moat" gate, deterministic.

The SEED feed is near-free because it reuses pages the research stage already fetched — but that
convenience must not buy a claim a free pass. These tests run the REAL seed path
(``GroundingSeeder`` → ``CorpusIngestor`` → corpus) and then verify against that corpus, proving the
P6.2 trust floor holds identically on SEEDED evidence (seeded is not the same as trusted):

1. A lone open-web SEED source cannot ground a HIGH-risk claim — the worst case (StubSupportAssessor
   always SUPPORTS, so only the floor can cut it).
2. SEEDED evidence corroborated across two independent domains clears the floor — seeding that
   achieves cross-source coverage *does* ground claims.
3. The near-free win: a single trusted SEED grounds a LOW-risk claim an EMPTY corpus would cut —
   so reusing what research already read actually flips claims from CUT to SUPPORTED.

All run on every commit (no model, no network); the live, key-gated build proof is in
``test_seed_feed_eval`` (added with the variant task).
"""

from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.seeding import GroundingSeeder, SeedReport
from lunaris_agent.subagents.standard_researcher import SeedSource
from lunaris_grounding import (
    CorpusIngestor,
    CredibilityScorer,
    InMemoryCorpusStore,
    InMemorySourceAuthorityStore,
    PgVectorRetriever,
    StubEmbedder,
    StubSupportAssessor,
    Verifier,
)
from lunaris_runtime.schema import AcquisitionMode, Claim, RiskTier, TrustTier, VerifierStatus

_DIM = 96
_COURSE = "seed-course"
_FETCHED_AT = "2026-06-04T00:00:00+00:00"
# Wrong but topically-relevant (the classic probe): Dijkstra's algorithm does NOT handle negative
# edge weights. A seeded SEO page repeats it — only the verifier's trust floor stops it grounding.
_WRONG_CLAIM = "Dijkstra's algorithm works correctly with negative edge weights"


def _draft() -> CourseDraft:
    return CourseDraft(topic="Algorithms", course_id=_COURSE, run_id="run-seed")


async def _seed(corpus: InMemoryCorpusStore, seeds: list[SeedSource]) -> SeedReport:
    """Ingest the seeds into ``corpus`` through the real seeder + the same scorer discovery uses."""
    draft = _draft()
    draft.research_seeds = seeds
    seeder = GroundingSeeder(
        CorpusIngestor(
            StubEmbedder(dim=_DIM), corpus, scorer=CredibilityScorer(InMemorySourceAuthorityStore())
        )
    )
    return await seeder.seed(draft)


def _verifier(corpus: InMemoryCorpusStore) -> Verifier:
    # min_score=0.0 so retrieval never filters on the stub embedder — the floor, not relevance, is
    # what's under test. StubSupportAssessor always SUPPORTS, so a CUT can only come from the floor.
    return Verifier(
        PgVectorRetriever(StubEmbedder(dim=_DIM), corpus, min_score=0.0), StubSupportAssessor()
    )


async def test_a_seeded_open_source_cannot_ground_a_high_risk_claim() -> None:
    # Arrange — the research stage fetched ONE topical-but-wrong SEO page (classified OPEN); it is
    # seeded into the corpus, graded by the ingestor's scorer (credibility filled, tier stays OPEN).
    corpus = InMemoryCorpusStore()
    report = await _seed(
        corpus,
        [
            SeedSource(
                url="https://seo-slop.example/dijkstra-negative-weights",
                text=f"{_WRONG_CLAIM}. Dijkstra, repeated for SEO. " * 3,
                trust_tier=TrustTier.OPEN,
                fetched_at=_FETCHED_AT,
            )
        ],
    )
    assert report.sources_seeded == 1
    claim = Claim(text=_WRONG_CLAIM)

    # Act — verify the wrong claim at HIGH risk against the seeded corpus.
    await _verifier(corpus).verify([claim], risk_tier=RiskTier.HIGH, course_id=_COURSE)

    # Assert — the moat holds on seeded evidence: a lone OPEN source can't ground a high-stakes
    # claim, even though the assessor supported it — the SEED feed didn't invert the floor.
    assert claim.verifier_status is VerifierStatus.CUT
    (summary,) = await corpus.list_sources_for_course(_COURSE)
    assert summary.acquisition_mode is AcquisitionMode.SEED
    assert summary.trust_tier is TrustTier.OPEN  # graded, not blindly trusted


async def test_seeded_evidence_across_two_domains_clears_the_high_risk_floor() -> None:
    # Arrange — research fetched the claim on TWO independent domains; both are seeded. Distinct
    # bodies so both chunks are retrieved, not deduped into one.
    corpus = InMemoryCorpusStore()
    claim_text = "binary search runs in logarithmic time by halving the sorted array"
    report = await _seed(
        corpus,
        [
            SeedSource(
                url="https://one.example/bs",
                text="Binary search halves the sorted array — logarithmic time, source one.",
                trust_tier=TrustTier.OPEN,
                fetched_at=_FETCHED_AT,
            ),
            SeedSource(
                url="https://two.example/bs",
                text="Logarithmic time: binary search halves the sorted array, source two.",
                trust_tier=TrustTier.OPEN,
                fetched_at=_FETCHED_AT,
            ),
        ],
    )
    assert report.sources_seeded == 2
    claim = Claim(text=claim_text)

    # Act
    await _verifier(corpus).verify([claim], risk_tier=RiskTier.HIGH, course_id=_COURSE)

    # Assert — corroboration across two seeded domains clears the floor (seeding that achieves
    # cross-source coverage grounds the claim, exactly like discovery), and both sources were
    # recorded as SEED-acquired (the mode tag, not just the verdict, is the structural invariant).
    assert claim.verifier_status is VerifierStatus.SUPPORTED
    summaries = await corpus.list_sources_for_course(_COURSE)
    assert len(summaries) == 2
    assert all(s.acquisition_mode is AcquisitionMode.SEED for s in summaries)


async def test_a_single_trusted_seed_grounds_a_low_risk_claim_an_empty_corpus_would_cut() -> None:
    # Arrange — the near-free win. Same claim, two corpora: empty vs. seeded from one official page
    # the research stage already read. Both verified at LOW risk with the always-SUPPORT assessor,
    # the only difference is whether the corpus holds retrievable evidence.
    claim_text = "the Canadian Language Benchmarks define listening competencies at each level"
    empty_corpus = InMemoryCorpusStore()
    seeded_corpus = InMemoryCorpusStore()
    await _seed(
        seeded_corpus,
        [
            SeedSource(
                url="https://www.canada.ca/clb-listening",
                text="Canadian Language Benchmarks define listening competencies at each level.",
                trust_tier=TrustTier.OFFICIAL,
                fetched_at=_FETCHED_AT,
            )
        ],
    )
    empty_claim = Claim(text=claim_text)
    seeded_claim = Claim(text=claim_text)

    # Act
    await _verifier(empty_corpus).verify([empty_claim], risk_tier=RiskTier.LOW, course_id=_COURSE)
    await _verifier(seeded_corpus).verify([seeded_claim], risk_tier=RiskTier.LOW, course_id=_COURSE)

    # Assert — an empty corpus cuts the claim (no evidence to ground it); seeding the page research
    # already fetched flips it to SUPPORTED, with no extra fetch — and it is recorded as an OFFICIAL
    # SEED source (the provenance a learner can audit in the Corpus tab).
    assert empty_claim.verifier_status is VerifierStatus.CUT
    assert seeded_claim.verifier_status is VerifierStatus.SUPPORTED
    (seeded_summary,) = await seeded_corpus.list_sources_for_course(_COURSE)
    assert seeded_summary.acquisition_mode is AcquisitionMode.SEED
    assert seeded_summary.trust_tier is TrustTier.OFFICIAL


async def test_an_empty_seed_list_ingests_nothing() -> None:
    # Arrange — no research seeds (the no-key / unavailable-research path).
    corpus = InMemoryCorpusStore()

    # Act
    report = await _seed(corpus, [])

    # Assert — a no-op pass: nothing ingested, the corpus stays empty (not a partial write).
    assert report.sources_seeded == 0
    assert report.chunks_ingested == 0
    assert await corpus.list_sources_for_course(_COURSE) == []


async def test_a_blocked_seed_cannot_ground_even_a_low_risk_claim() -> None:
    # Arrange — defense-in-depth: research drops BLOCKED domains before they ever become seeds, but
    # if a blocked-tier source did reach the seeder, the floor must still refuse it at every risk
    # level (BLOCKED is never evidence). LOW risk normally accepts any non-blocked source.
    corpus = InMemoryCorpusStore()
    claim_text = "blocked sources must never ground a claim, no matter how on-topic"
    await _seed(
        corpus,
        [
            SeedSource(
                url="https://bit.ly/blocked",  # a denylisted shortener → BLOCKED
                text=f"{claim_text}. Repeated for retrieval. " * 3,
                trust_tier=TrustTier.BLOCKED,
                fetched_at=_FETCHED_AT,
            )
        ],
    )
    claim = Claim(text=claim_text)

    # Act
    await _verifier(corpus).verify([claim], risk_tier=RiskTier.LOW, course_id=_COURSE)

    # Assert — defense-in-depth, not a pre-filter: the BLOCKED chunk IS ingested (so the CUT is the
    # floor refusing it, not an empty corpus), yet even at LOW risk it cannot ground the claim.
    (summary,) = await corpus.list_sources_for_course(_COURSE)
    assert summary.trust_tier is TrustTier.BLOCKED
    assert claim.verifier_status is VerifierStatus.CUT
