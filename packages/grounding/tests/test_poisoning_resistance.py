"""P6.2 (T5) — the headline "moat defends itself" gates, deterministic + per-commit.

The confirmation-bias trap (plan §1/§4): an author asserts X, a single SEO/AI-slop page also says X,
and a naive assessor rubber-stamps it. These tests prove the deterministic trust floor (T3) closes
that trap WITHOUT a model or a live corpus — they run on every commit (the live, key-gated variants
live in ``test_poisoning_resistance_eval.py``). Two invariants:

1. Poisoning resistance — a lone, low-trust source can't ground a HIGH-risk claim even when the
   assessor supports it; genuine cross-source agreement or a curated source still can.
2. Label-bias — the assessor is BLIND to a source's trust label (§10): the trust gate is applied by
   the Verifier, never by the judge, so the verdict can't be biased by an authority badge.
"""

from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    CredibilityScorer,
    InMemoryCorpusStore,
    InMemorySourceAuthorityStore,
    PgVectorRetriever,
    SourceAuthority,
    StubEmbedder,
    StubSupportAssessor,
    Verifier,
    render_evidence,
)
from lunaris_grounding.evidence import Evidence
from lunaris_runtime.schema import (
    AuthorityKind,
    Citation,
    Claim,
    RiskTier,
    TrustTier,
    VerifierStatus,
)

_DIM = 96
_COURSE = "poison-course"
# A deliberately WRONG but topically-relevant claim (the classic poisoning probe): Dijkstra's
# algorithm does NOT work with negative edge weights. A naive assessor pattern-matching the words
# would happily "support" it — only the trust floor stops it.
_WRONG_CLAIM = "Dijkstra's algorithm works correctly with negative edge weights"


def _authorities() -> InMemorySourceAuthorityStore:
    return InMemorySourceAuthorityStore(
        [
            SourceAuthority(
                domain="en.wikipedia.org", kind=AuthorityKind.SPINE, trust_tier=TrustTier.REPUTABLE
            ),
        ]
    )


def _scoring_ingestor(store: InMemoryCorpusStore) -> CorpusIngestor:
    return CorpusIngestor(StubEmbedder(dim=_DIM), store, scorer=CredibilityScorer(_authorities()))


def _verifier(store: InMemoryCorpusStore) -> Verifier:
    # min_score=0.0 so the stub embedder's cosine never filters the source out — the floor, not
    # retrieval relevance, is what's under test.
    return Verifier(
        PgVectorRetriever(StubEmbedder(dim=_DIM), store, min_score=0.0), StubSupportAssessor()
    )


async def test_a_single_poisoned_open_source_is_cut_at_high_risk() -> None:
    # Arrange — a lone open-web page asserting the wrong claim is ingested + scored (→ OPEN tier).
    store = InMemoryCorpusStore()
    await _scoring_ingestor(store).ingest(
        [
            CandidateSource(
                kc_id="dijkstra",
                text=f"{_WRONG_CLAIM}. This SEO article repeats the claim several times.",
                url="https://seo-slop.example/dijkstra-negative-weights",
                course_id=_COURSE,
            )
        ]
    )
    claim = Claim(text=_WRONG_CLAIM)

    # Act — verify at HIGH risk against the course's own corpus.
    await _verifier(store).verify([claim], risk_tier=RiskTier.HIGH, course_id=_COURSE)

    # Assert — the moat holds: a single low-trust source does not ground a high-stakes claim, even
    # though the (naive) assessor supported it. This is the poisoning-resistance guarantee.
    assert claim.verifier_status is VerifierStatus.CUT


async def test_the_same_poison_is_down_ranked_to_open_with_low_credibility() -> None:
    # Arrange — ingest the poisoned source, then read its scored provenance back off the citation.
    store = InMemoryCorpusStore()
    await _scoring_ingestor(store).ingest(
        [
            CandidateSource(
                kc_id="dijkstra",
                text=f"{_WRONG_CLAIM}. Repeated filler. " * 3,
                url="https://seo-slop.example/dijkstra",
                course_id=_COURSE,
            )
        ]
    )
    [query] = await StubEmbedder(dim=_DIM).embed([_WRONG_CLAIM])

    # Act — read the stored chunk directly off the store: the assertion is about the scored
    # provenance on the chunk, before any assessor opinion, which the verify() path doesn't expose.
    [evidence] = await store.match(query, k=1, course_id=_COURSE)

    # Assert — the scorer down-ranks the unknown SEO domain to OPEN, below the curated tiers, so the
    # trust floor (which needs >= REPUTABLE or corroboration) rejects it at HIGH.
    assert evidence.citation.trust_tier is TrustTier.OPEN
    assert evidence.citation.credibility is not None
    assert evidence.citation.credibility < 0.70  # below the HIGH credibility floor


async def test_a_claim_corroborated_across_two_domains_survives_high_risk() -> None:
    # Arrange — the claim is corroborated by two INDEPENDENT domains. Distinct bodies (two chunks,
    # not one deduped chunk) that both share the claim's vocabulary, so both are retrieved.
    store = InMemoryCorpusStore()
    claim_text = "binary search runs in logarithmic time by halving the sorted array"
    await _scoring_ingestor(store).ingest(
        [
            CandidateSource(
                kc_id="kc",
                text="Binary search halving the sorted array gives logarithmic time, source one.",
                url="https://one.example/a",
                course_id=_COURSE,
            ),
            CandidateSource(
                kc_id="kc",
                text="Logarithmic time follows because binary search halves the sorted array, two.",
                url="https://two.example/b",
                course_id=_COURSE,
            ),
        ]
    )
    claim = Claim(text=claim_text)

    # Act
    await _verifier(store).verify([claim], risk_tier=RiskTier.HIGH, course_id=_COURSE)

    # Assert — corroboration across two domains clears the floor.
    assert claim.verifier_status is VerifierStatus.SUPPORTED


async def test_a_single_open_source_still_grounds_a_low_risk_claim() -> None:
    # Arrange — risk-adaptivity: the same lone open-web source the HIGH floor rejects is fine at
    # LOW risk (recorded, not refused) — the floor adapts to the stakes, it isn't all-or-nothing.
    store = InMemoryCorpusStore()
    body = "A perfectly ordinary, low-stakes piece of grounding text retrieved for this claim."
    await _scoring_ingestor(store).ingest(
        [CandidateSource(kc_id="kc", text=body, url="https://blog.example/x", course_id=_COURSE)]
    )
    claim = Claim(text=body)

    # Act
    await _verifier(store).verify([claim], risk_tier=RiskTier.LOW, course_id=_COURSE)

    # Assert
    assert claim.verifier_status is VerifierStatus.SUPPORTED


def _ev(cid: str, *, tier: TrustTier | None, credibility: float | None) -> Evidence:
    citation = Citation(
        id=cid,
        title="t",
        snippet="the evidence body",
        url="https://x.example/p",
        trust_tier=tier,
        credibility=credibility,
    )
    return Evidence(citation=citation, score=0.9)


def test_the_assessor_prompt_is_blind_to_the_trust_label() -> None:
    # Arrange — the same evidence text, one carrying a high trust tier + credibility, one carrying
    # none. The judge must not see either: trust is the Verifier's job, not the LLM's (§10).
    labelled = [_ev("c1", tier=TrustTier.OFFICIAL, credibility=0.95)]
    unlabelled = [_ev("c1", tier=None, credibility=None)]

    # Act
    rendered_labelled = render_evidence(labelled)
    rendered_unlabelled = render_evidence(unlabelled)

    # Assert — byte-identical: the trust tier / credibility never enter the prompt, so the
    # verdict cannot be biased by an authority badge (the label-bias invariant).
    assert rendered_labelled == rendered_unlabelled
    assert (
        "the evidence body" in rendered_labelled
    )  # the snippet IS rendered (not silently dropped)
    assert "official" not in rendered_labelled.lower()
    assert "0.95" not in rendered_labelled
