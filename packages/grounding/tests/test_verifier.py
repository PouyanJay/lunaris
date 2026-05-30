from lunaris_grounding import (
    Evidence,
    StubEvidenceRetriever,
    StubSupportAssessor,
    Verifier,
)
from lunaris_runtime.schema import Citation, Claim, RiskTier, VerifierStatus


def _evidence(cid: str, score: float = 0.9) -> Evidence:
    return Evidence(citation=Citation(id=cid, title=f"Source {cid}", snippet="..."), score=score)


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
