import pytest
from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    Evidence,
    InMemoryCorpusStore,
    PgVectorRetriever,
    StubEmbedder,
    StubEvidenceRetriever,
    StubSupportAssessor,
    Support,
    Verifier,
)
from lunaris_runtime.schema import Citation, Claim, RiskTier, TrustTier, VerifierStatus


def _evidence(cid: str, score: float = 0.9) -> Evidence:
    return Evidence(citation=Citation(id=cid, title=f"Source {cid}", snippet="..."), score=score)


async def test_verifier_grounds_only_against_the_courses_own_corpus() -> None:
    # Arrange — a source ingested for course c1 (the end-to-end path: ingest → corpus → retriever).
    store = InMemoryCorpusStore()
    text = "Dijkstra relaxes edges."
    await CorpusIngestor(StubEmbedder(dim=64), store).ingest(
        [CandidateSource(kc_id="kc1", text=text, course_id="c1", source_id="s1")]
    )
    # min_score=0.0 so the stub embedder's cosine score is never filtered out (the default floor
    # would make this test fragile to the embedder); scoping, not relevance, is what's under test.
    retriever = PgVectorRetriever(StubEmbedder(dim=64), store, min_score=0.0)
    verifier = Verifier(retriever, StubSupportAssessor())

    # Act — verify the SAME claim scoped to c1 (the corpus's course) vs c2 (a different course).
    grounded = Claim(text=text)
    await verifier.verify([grounded], course_id="c1")
    foreign = Claim(text=text)
    await verifier.verify([foreign], course_id="c2")

    # Assert — grounded against its own course's evidence; cut for another course (no bleed). The
    # P6.1 payoff: a build verifies against THIS course's manually-ingested corpus.
    assert grounded.verifier_status is VerifierStatus.SUPPORTED
    assert grounded.supported_by is not None
    assert foreign.verifier_status is VerifierStatus.CUT


def _tiered(
    cid: str,
    *,
    tier: TrustTier | None = None,
    credibility: float | None = None,
    url: str | None = None,
    score: float = 0.9,
) -> Evidence:
    # All-None tier/credibility simulates a pre-P6.2 Citation (un-classified legacy evidence).
    citation = Citation(
        id=cid,
        title=f"Source {cid}",
        snippet="...",
        url=url,
        trust_tier=tier,
        credibility=credibility,
    )
    return Evidence(citation=citation, score=score)


# --- T3: the risk-tiered trust floor (orthogonal to the assessor-score threshold) -------------


async def test_high_risk_floor_cuts_a_low_trust_single_source() -> None:
    # Arrange — the assessor supports it, but the only evidence is an OPEN-tier single source with
    # no corroboration: it must not clear the HIGH trust floor (the §4c "T3-only, don't ship" rule).
    retriever = StubEvidenceRetriever(
        lambda _c: [
            _tiered("c1", tier=TrustTier.OPEN, credibility=0.6, url="https://blog.example/x")
        ]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a high-stakes claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert — the trust floor cuts it even though the assessor's score was high.
    assert claim.verifier_status is VerifierStatus.CUT


async def test_high_risk_floor_accepts_a_reputable_credible_source() -> None:
    # Arrange — a curated, credible source clears the floor at HIGH.
    retriever = StubEvidenceRetriever(
        lambda _c: [
            _tiered(
                "c1", tier=TrustTier.REPUTABLE, credibility=0.75, url="https://en.wikipedia.org/x"
            )
        ]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a high-stakes claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert
    assert claim.verifier_status is VerifierStatus.SUPPORTED
    assert claim.supported_by == "c1"


async def test_high_risk_floor_accepts_a_vouched_source() -> None:
    # Arrange — the learner vouched for it (manual ingest); a vouch clears the floor at HIGH.
    retriever = StubEvidenceRetriever(
        lambda _c: [
            _tiered("c1", tier=TrustTier.VOUCHED, credibility=0.85, url="https://notes.example/x")
        ]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a high-stakes claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert
    assert claim.verifier_status is VerifierStatus.SUPPORTED
    assert claim.supported_by == "c1"


async def test_high_risk_floor_cuts_a_reputable_source_below_the_credibility_floor() -> None:
    # Arrange — REPUTABLE clears the tier rank, but credibility 0.69 < the 0.70 floor and there's no
    # corroboration: the credibility arm of the HIGH gate must cut it (the AND, not just the tier).
    retriever = StubEvidenceRetriever(
        lambda _c: [
            _tiered(
                "c1", tier=TrustTier.REPUTABLE, credibility=0.69, url="https://en.wikipedia.org/x"
            )
        ]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a high-stakes claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert
    assert claim.verifier_status is VerifierStatus.CUT


async def test_high_risk_floor_cuts_an_official_source_with_no_credibility_score() -> None:
    # Arrange — a pre-P6.2 OFFICIAL citation (tier set by classify_domain at ingest, but the scorer
    # never ran → credibility None). Fail-secure: an unscored source can't clear the HIGH floor
    # with no corroboration. A regression canary if the scorer/ingest order changes.
    retriever = StubEvidenceRetriever(
        lambda _c: [_tiered("c1", tier=TrustTier.OFFICIAL, url="https://cdc.gov/x")]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a high-stakes claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert
    assert claim.verifier_status is VerifierStatus.CUT


# --- P5: official_only — a per-build trust floor that applies the curated-or-agreement gate at
# EVERY risk tier, not just HIGH (the "Official sources only" composer switch). --------------------


def _open_single_source() -> StubEvidenceRetriever:
    # One OPEN-tier source, credible enough for the assessor, no corroboration.
    return StubEvidenceRetriever(
        lambda _c: [
            _tiered("c1", tier=TrustTier.OPEN, credibility=0.6, url="https://blog.example/x")
        ]
    )


async def test_open_web_single_source_is_supported_at_low_risk_by_default() -> None:
    # Baseline (official_only off): at LOW risk the open web is recorded, not refused — this is the
    # claim the switch must be shown to cut, so pin the default first.
    verifier = Verifier(_open_single_source(), StubSupportAssessor())
    claim = Claim(text="a low-stakes claim")

    await verifier.verify([claim], risk_tier=RiskTier.LOW)

    assert claim.verifier_status is VerifierStatus.SUPPORTED


async def test_official_only_cuts_an_open_web_single_source_at_low_risk() -> None:
    # The switch raises the floor: the same LOW-risk claim backed only by a single open-web source
    # is now CUT — curated-or-agreement is demanded at every tier, not just HIGH.
    verifier = Verifier(_open_single_source(), StubSupportAssessor())
    claim = Claim(text="a low-stakes claim")

    await verifier.verify([claim], risk_tier=RiskTier.LOW, official_only=True)

    assert claim.verifier_status is VerifierStatus.CUT


async def test_official_only_accepts_a_curated_credible_source_at_low_risk() -> None:
    # A curated (reputable), credible source clears the raised floor at LOW — trusted content stays.
    retriever = StubEvidenceRetriever(
        lambda _c: [
            _tiered(
                "c1", tier=TrustTier.REPUTABLE, credibility=0.75, url="https://en.wikipedia.org/x"
            )
        ]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a low-stakes claim")

    await verifier.verify([claim], risk_tier=RiskTier.LOW, official_only=True)

    assert claim.verifier_status is VerifierStatus.SUPPORTED


async def test_official_only_keeps_a_claim_corroborated_across_independent_domains() -> None:
    # The safeguard against emptying the course: two independent open-web domains agreeing clears
    # the raised floor even without a curated source, so cross-source agreement survives the switch.
    retriever = StubEvidenceRetriever(
        lambda _c: [
            _tiered(
                "c1", tier=TrustTier.OPEN, credibility=0.6, url="https://a.example/x", score=0.95
            ),
            _tiered(
                "c2", tier=TrustTier.OPEN, credibility=0.6, url="https://b.example/y", score=0.9
            ),
        ]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a low-stakes claim")

    await verifier.verify([claim], risk_tier=RiskTier.LOW, official_only=True)

    assert claim.verifier_status is VerifierStatus.SUPPORTED


async def test_high_risk_floor_accepts_open_evidence_with_cross_source_agreement() -> None:
    # Arrange — two INDEPENDENT domains corroborate the claim. Authority emerges from agreement
    # (plan §4a): cross-source agreement clears the HIGH floor even for an open-web chosen source.
    evidence = [
        _tiered("c1", tier=TrustTier.OPEN, credibility=0.6, url="https://a.example/x"),
        _tiered("c2", tier=TrustTier.OPEN, credibility=0.6, url="https://b.example/y", score=0.8),
    ]
    verifier = Verifier(StubEvidenceRetriever(lambda _c: evidence), StubSupportAssessor())
    claim = Claim(text="a corroborated claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert — corroboration across two domains lifts it past the floor. (StubSupportAssessor picks
    # the top-scoring evidence; c2 scores 0.8 < c1's 0.9, so the chosen citation is c1.)
    assert claim.verifier_status is VerifierStatus.SUPPORTED
    assert claim.supported_by == "c1"


async def test_high_risk_floor_rejects_agreement_from_a_single_domain() -> None:
    # Arrange — two chunks but the SAME domain: not independent corroboration, so the single
    # poisoned-source case can't manufacture agreement from itself.
    evidence = [
        _tiered("c1", tier=TrustTier.OPEN, credibility=0.6, url="https://a.example/x"),
        _tiered("c2", tier=TrustTier.OPEN, credibility=0.6, url="https://a.example/y", score=0.8),
    ]
    verifier = Verifier(StubEvidenceRetriever(lambda _c: evidence), StubSupportAssessor())
    claim = Claim(text="a single-source claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert
    assert claim.verifier_status is VerifierStatus.CUT


async def test_blocked_evidence_never_supports_even_at_low_risk() -> None:
    # Arrange — a denylisted source. BLOCKED evidence is poison at any risk tier.
    retriever = StubEvidenceRetriever(
        lambda _c: [_tiered("c1", tier=TrustTier.BLOCKED, credibility=0.0, url="https://bit.ly/x")]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a claim from a blocked source")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.LOW)

    # Assert
    assert claim.verifier_status is VerifierStatus.CUT


async def test_low_risk_floor_accepts_a_single_open_source() -> None:
    # Arrange — at LOW risk the floor only excludes blocked sources; an open-web source is recorded.
    retriever = StubEvidenceRetriever(
        lambda _c: [
            _tiered("c1", tier=TrustTier.OPEN, credibility=0.6, url="https://blog.example/x")
        ]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a casual claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.LOW)

    # Assert
    assert claim.verifier_status is VerifierStatus.SUPPORTED


async def test_high_risk_floor_cuts_untiered_legacy_evidence() -> None:
    # Arrange — a pre-P6.2 citation (no tier, no credibility) with no corroboration. At HIGH it
    # can't clear the floor: un-classified evidence is treated as open web, not trusted by omission.
    retriever = StubEvidenceRetriever(lambda _c: [_tiered("c1", url="https://legacy.example/x")])
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a high-stakes legacy claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert
    assert claim.verifier_status is VerifierStatus.CUT


async def test_low_risk_accepts_untiered_legacy_evidence() -> None:
    # Arrange — backward-compat: LOW is unchanged for un-tiered (pre-P6.2) evidence.
    retriever = StubEvidenceRetriever(lambda _c: [_tiered("c1", url="https://legacy.example/x")])
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a casual legacy claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.LOW)

    # Assert
    assert claim.verifier_status is VerifierStatus.SUPPORTED


async def test_supported_claim_gets_citation_and_status() -> None:
    # Arrange — evidence exists for the claim
    retriever = StubEvidenceRetriever(lambda _c: [_evidence("c1")])
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="the sky is blue")

    # Act
    citations = await verifier.verify([claim])

    # Assert
    assert claim.verifier_status is VerifierStatus.SUPPORTED
    assert claim.supported_by == "c1"
    assert [c.id for c in citations] == ["c1"]


async def test_unsupported_claim_is_cut_not_left_live() -> None:
    # Arrange — no evidence for the claim
    verifier = Verifier(StubEvidenceRetriever(), StubSupportAssessor())
    claim = Claim(text="unsubstantiated assertion")

    # Act
    citations = await verifier.verify([claim])

    # Assert — publish gate: cut, no citation
    assert claim.verifier_status is VerifierStatus.CUT
    assert claim.supported_by is None
    assert citations == []


async def test_high_risk_threshold_cuts_weak_support() -> None:
    # Arrange — evidence exists but the assessor's score (0.7) is below the high bar (0.85)
    retriever = StubEvidenceRetriever(lambda _c: [_evidence("c1")])
    assessor = StubSupportAssessor(score_when_supported=0.7)
    verifier = Verifier(retriever, assessor)
    claim = Claim(text="risky medical claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert — high-stakes is stricter: weak support is cut
    assert claim.verifier_status is VerifierStatus.CUT


async def test_low_risk_threshold_accepts_same_support() -> None:
    # Arrange — same 0.7 support, low-stakes bar is 0.65
    retriever = StubEvidenceRetriever(lambda _c: [_evidence("c1")])
    verifier = Verifier(retriever, StubSupportAssessor(score_when_supported=0.7))
    claim = Claim(text="casual claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.LOW)

    # Assert
    assert claim.verifier_status is VerifierStatus.SUPPORTED


async def test_publish_gate_holds_across_mixed_claims() -> None:
    # Arrange — one supported, one unsupported
    def retrieve(claim_text: str) -> list[Evidence]:
        return [_evidence("c1")] if "good" in claim_text else []

    verifier = Verifier(StubEvidenceRetriever(retrieve), StubSupportAssessor())
    claims = [Claim(text="good claim"), Claim(text="bad claim")]

    # Act
    await verifier.verify(claims)

    # Assert — every claim is supported-or-cut (gate never raises)
    assert claims[0].verifier_status is VerifierStatus.SUPPORTED
    assert claims[1].verifier_status is VerifierStatus.CUT
    assert all(
        c.supported_by is not None or c.verifier_status is VerifierStatus.CUT for c in claims
    )


class _FailingRetriever:
    """Stands in for a grounding provider that is down / rate-limited."""

    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, _claim_text: str, *, course_id: str | None = None) -> list[Evidence]:
        self.calls += 1
        raise RuntimeError("voyageai.error.RateLimitError: 3 RPM exceeded")


class _SpyAssessor:
    def __init__(self) -> None:
        self.calls = 0

    async def assess(self, claim_text: str, evidence: list[Evidence]) -> Support:
        self.calls += 1
        return await StubSupportAssessor().assess(claim_text, evidence)


class _PartialRetriever:
    """Fails to retrieve evidence only for claims whose text contains ``boom``."""

    async def retrieve(self, claim_text: str, *, course_id: str | None = None) -> list[Evidence]:
        if "boom" in claim_text:
            raise RuntimeError("transient grounding outage")
        return [_evidence("c1")]


async def test_retriever_failure_fails_safe_to_cut_not_crash() -> None:
    # Arrange — the evidence retriever raises (e.g. embeddings provider rate-limited);
    # the verifier must uphold its contract (never ship an unsupported claim) by cutting,
    # not by propagating and taking down the whole course delivery.
    retriever = _FailingRetriever()
    assessor = _SpyAssessor()
    verifier = Verifier(retriever, assessor)
    claim = Claim(text="binary search runs in logarithmic time")

    # Act
    citations = await verifier.verify([claim])

    # Assert — fail-safe: claim cut, no citation, no crash, assessor never reached
    assert claim.verifier_status is VerifierStatus.CUT
    assert claim.supported_by is None
    assert citations == []
    assert assessor.calls == 0


async def test_one_retriever_failure_does_not_sink_other_claims() -> None:
    # Arrange — a retriever that fails only for one claim
    verifier = Verifier(_PartialRetriever(), StubSupportAssessor())
    claims = [Claim(text="good claim"), Claim(text="boom claim")]

    # Act
    citations = await verifier.verify(claims)

    # Assert — the healthy claim is still supported; the failed one is cut
    assert claims[0].verifier_status is VerifierStatus.SUPPORTED
    assert claims[1].verifier_status is VerifierStatus.CUT
    assert [c.id for c in citations] == ["c1"]


# --- T6: variant coverage — the trust-floor decision matrix + boundaries ----------------------


@pytest.mark.parametrize(
    ("tier", "credibility", "risk", "expected"),
    [
        # LOW risk: every tier except BLOCKED is recorded.
        (TrustTier.OFFICIAL, 0.9, RiskTier.LOW, VerifierStatus.SUPPORTED),
        (TrustTier.REPUTABLE, 0.75, RiskTier.LOW, VerifierStatus.SUPPORTED),
        (TrustTier.VOUCHED, 0.85, RiskTier.LOW, VerifierStatus.SUPPORTED),
        (TrustTier.OPEN, 0.5, RiskTier.LOW, VerifierStatus.SUPPORTED),
        (None, None, RiskTier.LOW, VerifierStatus.SUPPORTED),
        (TrustTier.BLOCKED, 0.0, RiskTier.LOW, VerifierStatus.CUT),
        # HIGH risk: only curated-or-better AND credible clears a single source.
        (TrustTier.OFFICIAL, 0.9, RiskTier.HIGH, VerifierStatus.SUPPORTED),
        (TrustTier.REPUTABLE, 0.75, RiskTier.HIGH, VerifierStatus.SUPPORTED),
        (TrustTier.VOUCHED, 0.85, RiskTier.HIGH, VerifierStatus.SUPPORTED),
        (TrustTier.OPEN, 0.65, RiskTier.HIGH, VerifierStatus.CUT),
        (None, None, RiskTier.HIGH, VerifierStatus.CUT),
        (TrustTier.BLOCKED, 0.0, RiskTier.HIGH, VerifierStatus.CUT),
    ],
)
async def test_trust_floor_decision_matrix(
    tier: TrustTier | None, credibility: float | None, risk: RiskTier, expected: VerifierStatus
) -> None:
    # Arrange — a single source of the given tier/credibility (no corroboration).
    retriever = StubEvidenceRetriever(
        lambda _c: [_tiered("c1", tier=tier, credibility=credibility, url="https://x.example/p")]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a claim")

    # Act
    await verifier.verify([claim], risk_tier=risk)

    # Assert
    assert claim.verifier_status is expected


async def test_high_risk_floor_accepts_exactly_at_the_credibility_boundary() -> None:
    # Arrange — REPUTABLE with credibility exactly 0.70 (the floor uses >=, so this clears).
    retriever = StubEvidenceRetriever(
        lambda _c: [
            _tiered("c1", tier=TrustTier.REPUTABLE, credibility=0.70, url="https://r.example/p")
        ]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a high-stakes claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert
    assert claim.verifier_status is VerifierStatus.SUPPORTED


async def test_a_blocked_domain_does_not_count_toward_cross_source_agreement() -> None:
    # Arrange — the chosen OPEN source plus a second domain that is BLOCKED. A denylisted source is
    # poison, not a corroborator, so this is one voice, not agreement → cut at HIGH.
    evidence = [
        _tiered("c1", tier=TrustTier.OPEN, credibility=0.6, url="https://open.example/x"),
        _tiered("c2", tier=TrustTier.BLOCKED, credibility=0.0, url="https://bit.ly/y", score=0.5),
    ]
    verifier = Verifier(StubEvidenceRetriever(lambda _c: evidence), StubSupportAssessor())
    claim = Claim(text="a claim corroborated only by a blocked source")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert
    assert claim.verifier_status is VerifierStatus.CUT


def test_verifier_exposes_its_retriever() -> None:
    # The retriever is read-only on the verifier so grounded authoring (CQ Phase 1.5) can retrieve
    # from the SAME corpus the gate checks against, without a second retriever or a loosened gate.
    retriever = StubEvidenceRetriever(lambda claim: [])

    verifier = Verifier(retriever, StubSupportAssessor())

    assert verifier.retriever is retriever
