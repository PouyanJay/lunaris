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
    ScholarlyRecord,
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
                domain="cochranelibrary.com",
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

    # Assert — an unknown domain is OPEN (earns trust later), never "trusted by omission". The exact
    # open-web credibility depends on the extraction-quality nudge, pinned in the blend tests below.
    assert scored.trust_tier is TrustTier.OPEN
    assert 0.0 < scored.credibility < 1.0


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
    # Arrange — cochranelibrary.com is a MEDICINE PACK with no gov/edu/int label of its own; a
    # candidate carries no field, so the pack must NOT promote it (field-scoped scoring is deferred
    # to T2). With no table hit and no label, it falls back to the open-web default.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://cochranelibrary.com/review/x")

    # Act
    scored = await scorer.score(source)

    # Assert — a pack hit is inert until a run's field is plumbed through (T2/T3): it falls to the
    # open-web blend (thin text → below the 0.50 prior), not the pack's OFFICIAL prior.
    assert scored.trust_tier is TrustTier.OPEN
    assert scored.credibility < 0.5


async def test_scorer_falls_back_to_the_gov_label_heuristic_for_an_untabled_domain() -> None:
    # Arrange — a government domain NOT in the authority table. The scorer composes the table with
    # classify_domain's deterministic label heuristic, so an authoritative domain is recognised even
    # before anyone curates it into the spine.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://www.cancer.gov/about")

    # Act
    scored = await scorer.score(source)

    # Assert — a .gov label reads OFFICIAL via the heuristic fallback (not the open-web default).
    assert scored.trust_tier is TrustTier.OFFICIAL
    assert scored.credibility == pytest.approx(0.90)


async def test_scorer_falls_back_to_the_edu_label_heuristic_for_an_untabled_domain() -> None:
    # Arrange — an academic domain not in the table.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://cs.stanford.edu/notes")

    # Act
    scored = await scorer.score(source)

    # Assert — .edu reads REPUTABLE via the heuristic fallback.
    assert scored.trust_tier is TrustTier.REPUTABLE
    assert scored.credibility == pytest.approx(0.75)


async def test_scorer_blocks_a_code_denylisted_shortener_not_in_the_table() -> None:
    # Arrange — tinyurl.com is in classify_domain's in-code denylist baseline but NOT in this test's
    # authority table. The two denylist layers are additive: the code baseline still BLOCKs it via
    # the fallback, so a shortener can't slip through just because no one curated it into the table.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://tinyurl.com/abc")

    # Act
    scored = await scorer.score(source)

    # Assert
    assert scored.trust_tier is TrustTier.BLOCKED
    assert scored.credibility == pytest.approx(0.0)


async def test_scorer_blocks_an_internal_ip_via_the_ssrf_guard() -> None:
    # Arrange — a link to a cloud-metadata endpoint. classify_domain's SSRF guard (kept in code)
    # must still BLOCK it through the scorer's fallback, with zero credibility.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="http://169.254.169.254/latest/meta-data/")

    # Act
    scored = await scorer.score(source)

    # Assert
    assert scored.trust_tier is TrustTier.BLOCKED
    assert scored.credibility == pytest.approx(0.0)


async def test_scorer_matches_a_subdomain_to_its_authority() -> None:
    # Arrange — a subdomain of a seeded spine domain should inherit the parent's tier.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://m.en.wikipedia.org/wiki/X")

    # Act
    scored = await scorer.score(source)

    # Assert — the subdomain inherits the parent's full scored verdict (tier + prior).
    assert scored.trust_tier is TrustTier.REPUTABLE
    assert scored.credibility == pytest.approx(0.75)


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


# --- T2: the credibility blend (extraction quality) + the scholarly-registry seam --------------

# A long, clean body (letters + spaces only, well past the substantive-length floor) → extraction
# quality ~= 1.0; a single char → quality ~= 0. Used to drive the open-web nudge to its extremes.
_SUBSTANTIVE_TEXT = "binary search halves the sorted range on every step " * 12


async def test_blend_nudges_open_credibility_up_for_substantive_text() -> None:
    # Arrange — an open-web domain with a clean, substantial body.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text=_SUBSTANTIVE_TEXT, url="https://blog.example/post")

    # Act
    scored = await scorer.score(source)

    # Assert — extraction quality nudges the open-web prior (0.50) up by the full +0.15.
    assert scored.trust_tier is TrustTier.OPEN
    assert scored.credibility == pytest.approx(0.65)


async def test_blend_nudges_open_credibility_down_for_thin_text() -> None:
    # Arrange — the same open-web domain but a one-char stub (a nav-sludge / empty-scrape proxy).
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://blog.example/post")

    # Act
    scored = await scorer.score(source)

    # Assert — thin text pushes the open-web prior down: quality ~0.002, nudge ~-0.149, so ~0.35.
    assert scored.trust_tier is TrustTier.OPEN
    assert scored.credibility == pytest.approx(0.3506, abs=1e-3)


async def test_blend_does_not_penalize_a_curated_tier_for_thin_text() -> None:
    # Arrange — a spine (REPUTABLE) source with a thin body. A curated tier is trusted at its prior;
    # page shape does not second-guess it (only the uncertain open web is nudged).
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text="t", url="https://en.wikipedia.org/wiki/X")

    # Act
    scored = await scorer.score(source)

    # Assert — REPUTABLE prior is returned unchanged despite the thin extraction.
    assert scored.credibility == pytest.approx(0.75)


async def test_blend_scores_a_blocked_source_zero_even_with_clean_text() -> None:
    # Arrange — a denylisted domain with an otherwise pristine body.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(kc_id="kc1", text=_SUBSTANTIVE_TEXT, url="https://bit.ly/x")

    # Act
    scored = await scorer.score(source)

    # Assert — a blocked source earns no credibility, however cleanly it extracts.
    assert scored.trust_tier is TrustTier.BLOCKED
    assert scored.credibility == pytest.approx(0.0)


class _RecordingRegistry:
    """A scholarly registry that confirms a peer-reviewed record for every URL (test seam)."""

    async def lookup(self, url: str) -> ScholarlyRecord | None:
        return ScholarlyRecord(venue="Journal of Examples", doi="10.0/x")


async def test_registry_floors_an_unknown_domain_to_reputable() -> None:
    # Arrange — an unknown open-web domain that the registry confirms is a real peer-reviewed paper.
    scorer = CredibilityScorer(_authorities(), registry=_RecordingRegistry())
    source = CandidateSource(
        kc_id="kc1", text=_SUBSTANTIVE_TEXT, url="https://unknown-journal.example/p"
    )

    # Act
    scored = await scorer.score(source)

    # Assert — an unknown host serving a real paper is floored to REPUTABLE, not left open web.
    assert scored.trust_tier is TrustTier.REPUTABLE
    assert scored.credibility == pytest.approx(0.75)


async def test_stub_registry_leaves_an_unknown_domain_open() -> None:
    # Arrange — the default (stub) registry resolves nothing, so the domain stays open web.
    scorer = CredibilityScorer(_authorities())
    source = CandidateSource(
        kc_id="kc1", text=_SUBSTANTIVE_TEXT, url="https://unknown-journal.example/p"
    )

    # Act
    scored = await scorer.score(source)

    # Assert — no record → open web; the substantive body keeps it at the +0.15 nudge (contrast the
    # registry-floored case above, which would be REPUTABLE at 0.75).
    assert scored.trust_tier is TrustTier.OPEN
    assert scored.credibility == pytest.approx(0.65)
