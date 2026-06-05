"""Doc-accuracy tests for the P6 grounding documentation (the docs TDD steering wheel).

These tests pin the user-facing grounding docs to the code they describe, so the docs cannot
silently rot when the enums, env keys, or module layout change. They read the repo-root docs as
text and reflect on the live runtime enums / secret registry / filesystem — no mocks, real layers.

The home for cross-cutting repo-level documentation tests; collected via ``testpaths`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GROUNDING_MODEL = _REPO_ROOT / "documentation" / "grounding-model.md"


def _require_doc(doc: Path) -> None:
    assert doc.exists(), f"expected documentation file is missing: {doc.relative_to(_REPO_ROOT)}"


def _read(doc: Path) -> str:
    _require_doc(doc)
    return doc.read_text(encoding="utf-8")


def test_grounding_model_documents_every_acquisition_mode() -> None:
    # Arrange — lowercased so a mode written as prose ("Manual mode") still matches its value.
    text = _read(_GROUNDING_MODEL).lower()

    # Act
    missing = [mode.value for mode in AcquisitionMode if mode.value not in text]

    # Assert
    assert not missing, f"grounding-model.md omits acquisition modes: {missing}"


def test_grounding_model_documents_every_trust_tier() -> None:
    # Arrange
    text = _read(_GROUNDING_MODEL).lower()

    # Act — the trust tiers are the spine of the trust model; every one must be named.
    missing = [tier.value for tier in TrustTier if tier.value not in text]

    # Assert
    assert not missing, f"grounding-model.md omits trust tiers: {missing}"


def test_grounding_model_documents_every_source_type() -> None:
    # Arrange — source types render with spaces or hyphens in prose ("peer-reviewed"); normalise both.
    text = _read(_GROUNDING_MODEL).lower().replace("-", " ").replace("_", " ")

    # Act
    missing = [
        source_type.value
        for source_type in SourceType
        if source_type.value.replace("_", " ") not in text
    ]

    # Assert
    assert not missing, f"grounding-model.md omits source types: {missing}"


def test_grounding_model_states_the_high_risk_credibility_floor() -> None:
    # Arrange — the documented floor must match the verifier's constant, or the doc lies about the moat.
    from lunaris_grounding.verifier import _HIGH_CREDIBILITY_FLOOR

    text = _read(_GROUNDING_MODEL)

    # Act / Assert
    assert f"{_HIGH_CREDIBILITY_FLOOR:.2f}" in text, (
        f"grounding-model.md must state the HIGH-risk credibility floor ({_HIGH_CREDIBILITY_FLOOR:.2f})"
    )
