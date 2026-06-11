"""The verifier's tunable gates (support thresholds, credibility floor, corroboration minimum)
as one injected value object — recalibrating against the poisoning eval's FPR is configuration,
not a code edit."""

import pytest
from lunaris_grounding import (
    Evidence,
    StubEvidenceRetriever,
    StubSupportAssessor,
    VerificationThresholds,
    Verifier,
)
from lunaris_runtime.schema import Citation, Claim, VerifierStatus


def _evidence(cid: str = "c1", score: float = 0.9) -> Evidence:
    return Evidence(citation=Citation(id=cid, title=f"Source {cid}", snippet="..."), score=score)


def test_default_thresholds_keep_the_calibrated_values() -> None:
    # The values the moat was calibrated with (P6.2) — changing a default is a deliberate act
    # that must show up in this test, the docs, and the poisoning eval together.
    thresholds = VerificationThresholds()
    assert (thresholds.high_support, thresholds.low_support) == (0.85, 0.65)
    assert thresholds.high_credibility_floor == 0.70
    assert thresholds.min_corroborating_domains == 2


async def test_custom_support_threshold_changes_the_verdict() -> None:
    # Arrange — identical evidence + assessor score (0.7); only the injected threshold differs.
    retriever = StubEvidenceRetriever(lambda _claim: [_evidence()])
    assessor = StubSupportAssessor(score_when_supported=0.7)
    lenient = Verifier(retriever, assessor)  # default LOW threshold 0.65 → 0.7 clears it
    strict = Verifier(retriever, assessor, thresholds=VerificationThresholds(low_support=0.8))
    lenient_claim, strict_claim = (
        Claim(text="Dijkstra relaxes edges."),
        Claim(text="Dijkstra relaxes edges."),
    )

    # Act
    await lenient.verify([lenient_claim])
    await strict.verify([strict_claim])

    # Assert — the gate moved with the injected threshold, nothing else changed.
    assert lenient_claim.verifier_status is VerifierStatus.SUPPORTED
    assert strict_claim.verifier_status is VerifierStatus.CUT


def test_thresholds_from_env_override_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("LUNARIS_VERIFIER_HIGH_SUPPORT", "0.9")
    monkeypatch.setenv("LUNARIS_VERIFIER_LOW_SUPPORT", "0.5")
    monkeypatch.setenv("LUNARIS_VERIFIER_HIGH_CREDIBILITY_FLOOR", "0.6")
    monkeypatch.setenv("LUNARIS_VERIFIER_MIN_CORROBORATING_DOMAINS", "3")

    # Act
    thresholds = VerificationThresholds.from_env()

    # Assert
    assert thresholds == VerificationThresholds(
        high_support=0.9,
        low_support=0.5,
        high_credibility_floor=0.6,
        min_corroborating_domains=3,
    )


def test_zero_is_a_legitimate_env_override_not_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — "0" is falsy as a string; it must still override (only unset/empty falls back).
    monkeypatch.setenv("LUNARIS_VERIFIER_LOW_SUPPORT", "0")
    monkeypatch.setenv("LUNARIS_VERIFIER_HIGH_CREDIBILITY_FLOOR", "")

    # Act
    thresholds = VerificationThresholds.from_env()

    # Assert — zero applied; the empty var kept its calibrated default.
    assert thresholds.low_support == 0.0
    assert thresholds.high_credibility_floor == VerificationThresholds().high_credibility_floor


def test_thresholds_from_env_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — none of the tuning vars set.
    for name in (
        "LUNARIS_VERIFIER_HIGH_SUPPORT",
        "LUNARIS_VERIFIER_LOW_SUPPORT",
        "LUNARIS_VERIFIER_HIGH_CREDIBILITY_FLOOR",
        "LUNARIS_VERIFIER_MIN_CORROBORATING_DOMAINS",
    ):
        monkeypatch.delenv(name, raising=False)

    # Act / Assert
    assert VerificationThresholds.from_env() == VerificationThresholds()
