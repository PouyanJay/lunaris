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


async def test_permissive_trust_floor_passes_a_tiered_citation() -> None:
    # Arrange — a credible, tiered citation. The T0 trust floor is permissive (it logs the tier but
    # never blocks), so a supported claim stays SUPPORTED. T3 makes this gate strict by risk tier;
    # this pins the seam's current behaviour so that change is visible when it lands.
    citation = Citation(
        id="c1", title="Source", snippet="...", trust_tier=TrustTier.OPEN, credibility=0.5
    )
    retriever = StubEvidenceRetriever(lambda _c: [Evidence(citation=citation, score=0.9)])
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="a grounded claim")

    # Act
    await verifier.verify([claim], risk_tier=RiskTier.HIGH)

    # Assert — the permissive floor does not block a low-tier citation (yet).
    assert claim.verifier_status is VerifierStatus.SUPPORTED
    assert claim.supported_by == "c1"


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
