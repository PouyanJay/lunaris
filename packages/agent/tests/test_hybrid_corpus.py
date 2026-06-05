"""P6.4 (T4) — the hybrid corpus: manual + auto + seed sources coexist in one per-course corpus.

The plan's "one corpus, three acquisition adapters writing the same shape" (§3). A learner uploads
sources (MANUAL, P6.1), the discovery agent can find them (AUTO, P6.3), and the build can seed them
from research it already fetched (SEED, P6.4) — all into the SAME course corpus, all graded by the
same gate, all retrievable together. These deterministic tests prove the three modes interoperate:
mixed provenance is auditable, scoped to the course, and jointly grounds a claim.

This file is specifically about their COEXISTENCE in one corpus. The single-mode adapter paths are
proven elsewhere: SEED in ``test_seed_poisoning``, MANUAL in the grounding folder-ingestor / corpus
suites, AUTO in ``test_discovery_poisoning`` / ``test_discovery_loop``. So here the MANUAL + AUTO
sources are constructed directly as ``CandidateSource``s (their adapters' shared output); only the
SEED path runs end-to-end through the real ``GroundingSeeder``. The corpus layer is what's tested.
"""

from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.seeding import GroundingSeeder
from lunaris_agent.subagents.standard_researcher import SeedSource
from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    CredibilityScorer,
    InMemoryCorpusStore,
    InMemorySourceAuthorityStore,
    PgVectorRetriever,
    StubEmbedder,
    StubSupportAssessor,
    Verifier,
)
from lunaris_runtime.schema import (
    AcquisitionMode,
    Claim,
    RiskTier,
    SourceType,
    TrustTier,
    VerifierStatus,
)

_DIM = 96
_COURSE = "hybrid-course"
_FETCHED_AT = "2026-06-04T00:00:00+00:00"
_CLAIM = "a hybrid corpus draws evidence from every acquisition mode at once"


def _candidate(url: str, mode: AcquisitionMode, tier: TrustTier) -> CandidateSource:
    """A source for the non-seed adapters (manual upload / auto-discovery), already mode-tagged.

    ``kc_id`` is set to the mode string only as a distinct, collision-free label — this test does
    not exercise KC alignment (the verifier matches by claim text, scoped to the course).
    """
    return CandidateSource(
        kc_id=mode.value,
        text=f"{_CLAIM}. Source via {mode.value}. " * 3,
        title=f"{mode.value} source",
        url=url,
        source_type=SourceType.WEB,
        trust_tier=tier,
        acquisition_mode=mode,
        fetched_at=_FETCHED_AT,
        course_id=_COURSE,
        source_id=f"src-{mode.value}",
    )


async def _fill_hybrid_corpus() -> InMemoryCorpusStore:
    """One course corpus filled from all three adapters through the single shared ingestor + gate.

    A manual upload + an auto-discovered page go straight through the ingestor; the seed goes via
    the real ``GroundingSeeder``. All carry the same ``course_id``, so they land in one per-course
    corpus, each graded by the ingestor's credibility scorer.
    """
    corpus = InMemoryCorpusStore()
    ingestor = CorpusIngestor(
        StubEmbedder(dim=_DIM), corpus, scorer=CredibilityScorer(InMemorySourceAuthorityStore())
    )
    await ingestor.ingest(
        [
            _candidate("https://upload.example/notes", AcquisitionMode.MANUAL, TrustTier.VOUCHED),
            _candidate("https://found.example/page", AcquisitionMode.AUTO, TrustTier.OPEN),
        ]
    )
    draft = CourseDraft(topic="Hybrid", course_id=_COURSE, run_id="run-hybrid")
    draft.research_seeds = [
        SeedSource(
            url="https://research.example/paper",
            text=f"{_CLAIM}. Source via seed. " * 3,
            title="seed source",
            trust_tier=TrustTier.OPEN,
            fetched_at=_FETCHED_AT,
        )
    ]
    await GroundingSeeder(ingestor).seed(draft)
    return corpus


async def test_manual_auto_and_seed_sources_share_one_course_corpus() -> None:
    # Arrange / Act — fill one course corpus from all three acquisition adapters.
    corpus = await _fill_hybrid_corpus()

    # Assert — all three modes coexist in the one course corpus, each carrying its own graded
    # provenance, and the manual upload keeps its VOUCHED tier (mixed provenance stays auditable).
    summaries = await corpus.list_sources_for_course(_COURSE)
    assert {s.acquisition_mode for s in summaries} == {
        AcquisitionMode.MANUAL,
        AcquisitionMode.AUTO,
        AcquisitionMode.SEED,
    }
    assert all(s.course_id == _COURSE for s in summaries)
    assert all(s.trust_tier is not None and s.credibility is not None for s in summaries)
    manual = next(s for s in summaries if s.acquisition_mode is AcquisitionMode.MANUAL)
    assert manual.trust_tier is TrustTier.VOUCHED
    assert manual.credibility is not None


async def test_a_claim_grounds_against_the_hybrid_corpus() -> None:
    # Arrange — a course corpus holding all three acquisition modes.
    corpus = await _fill_hybrid_corpus()
    claim = Claim(text=_CLAIM)

    # Act — verify against the hybrid corpus (min_score=0 so retrieval is not the variable here).
    verifier = Verifier(
        PgVectorRetriever(StubEmbedder(dim=_DIM), corpus, min_score=0.0), StubSupportAssessor()
    )
    await verifier.verify([claim], risk_tier=RiskTier.LOW, course_id=_COURSE)

    # Assert — the claim is grounded by the mixed-provenance corpus, scoped to this course.
    assert claim.verifier_status is VerifierStatus.SUPPORTED
    assert claim.supported_by is not None
