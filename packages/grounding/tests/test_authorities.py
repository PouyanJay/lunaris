"""P6.2 walking skeleton: the authority config → credibility scorer → ingest → citation path.

Proves the trust-scoring seam end-to-end through the grounding package: a seeded
``source_authorities`` row classifies a candidate's domain, the ``CredibilityScorer`` turns that
tier into a credibility prior, and both reach the corpus chunk + the citation untouched. The real
blended scorer (T2) and the risk-tiered trust floor (T3) build on this seam; here it only has to be
wired and carry a tier-derived credibility, not yet defend the moat.
"""

import pytest
from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    CredibilityScorer,
    InMemoryCorpusStore,
    InMemorySourceAuthorityStore,
    SourceAuthority,
    StubEmbedder,
)
from lunaris_runtime.schema import AcquisitionMode, AuthorityKind, SubjectField, TrustTier

_DIM = 64


def _authorities() -> InMemorySourceAuthorityStore:
    return InMemorySourceAuthorityStore(
        [
            SourceAuthority(
                domain="en.wikipedia.org", kind=AuthorityKind.SPINE, trust_tier=TrustTier.REPUTABLE
            ),
            SourceAuthority(
                domain="who.int",
                kind=AuthorityKind.PACK,
                field=SubjectField.MEDICINE,
                trust_tier=TrustTier.OFFICIAL,
            ),
            SourceAuthority(
                domain="bit.ly", kind=AuthorityKind.DENYLIST, trust_tier=TrustTier.BLOCKED
            ),
        ]
    )


async def test_scorer_tiers_a_candidate_from_the_spine() -> None:
    # Arrange — an unscored, untiered candidate whose host is a seeded spine authority.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(
        kc_id="kc1", text="t", url="https://en.wikipedia.org/wiki/Binary_search"
    )

    # Act
    scored = await scorer.score(source)

    # Assert — the table sets the tier; the tier maps to its credibility prior.
    assert scored.trust_tier is TrustTier.REPUTABLE
    assert scored.credibility == pytest.approx(0.75)


async def test_scorer_falls_back_to_open_for_an_unknown_domain() -> None:
    # Arrange — a domain not in the authority table (the general-web default).
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://random-blog.example/post")

    # Act
    scored = await scorer.score(source)

    # Assert — an unknown domain is OPEN (earns trust later), never "trusted by omission".
    assert scored.trust_tier is TrustTier.OPEN
    assert scored.credibility == pytest.approx(0.50)


async def test_scorer_marks_a_denylisted_domain_blocked_with_zero_credibility() -> None:
    # Arrange — a denylisted domain. BLOCKED → 0.0 is the foundation of the T5 poisoning gate.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://bit.ly/some-redirect")

    # Act
    scored = await scorer.score(source)

    # Assert
    assert scored.trust_tier is TrustTier.BLOCKED
    assert scored.credibility == pytest.approx(0.0)


async def test_scorer_does_not_apply_a_pack_tier_without_field_context() -> None:
    # Arrange — who.int is a MEDICINE PACK; a candidate carries no field, so the pack must NOT
    # promote it (field-scoped scoring is deferred to T2). It falls back to the open-web default.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://who.int/topics/x")

    # Act
    scored = await scorer.score(source)

    # Assert — a pack hit is inert until a run's field is plumbed through (T2/T3).
    assert scored.trust_tier is TrustTier.OPEN


async def test_scorer_matches_a_subdomain_to_its_authority() -> None:
    # Arrange — a subdomain of a seeded spine domain should inherit the parent's tier.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://m.en.wikipedia.org/wiki/X")

    # Act
    scored = await scorer.score(source)

    # Assert
    assert scored.trust_tier is TrustTier.REPUTABLE


async def test_scorer_fills_credibility_through_ingest_to_the_citation() -> None:
    # Arrange — wire the scorer into ingestion (an untiered spine source) end-to-end.
    store = InMemoryCorpusStore()
    text = "A grounding source on binary search and logarithmic time."
    ingestor = CorpusIngestor(
        StubEmbedder(dim=_DIM), store, scorer=CredibilityScorer(_authorities())
    )
    source = CandidateSource(
        kc_id="kc1", text=text, url="https://en.wikipedia.org/wiki/Binary_search", course_id="c1"
    )

    # Act
    await ingestor.ingest([source], run_id="run-skeleton")
    [query] = await StubEmbedder(dim=_DIM).embed([text])
    [evidence] = await store.match(query, k=1, course_id="c1")

    # Assert — the scorer's tier + credibility flow onto the chunk and the citation untouched.
    assert evidence.citation.trust_tier is TrustTier.REPUTABLE
    assert evidence.citation.credibility == pytest.approx(0.75)


async def test_scorer_preserves_an_already_vouched_source() -> None:
    # Arrange — a manually-ingested source (P6.1) arrives already VOUCHED with no credibility.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(
        kc_id="manual",
        text="user notes",
        trust_tier=TrustTier.VOUCHED,
        acquisition_mode=AcquisitionMode.MANUAL,
    )

    # Act
    scored = await scorer.score(source)

    # Assert — the user's vouch is preserved (not downgraded), with the VOUCHED prior assigned.
    assert scored.trust_tier is TrustTier.VOUCHED
    assert scored.credibility == pytest.approx(0.85)
