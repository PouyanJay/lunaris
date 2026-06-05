"""Doc-accuracy tests for the P6 grounding documentation (the docs TDD steering wheel).

These tests pin the user-facing grounding docs to the code they describe, so the docs cannot
silently rot when the enums, env keys, or module layout change. They read the repo-root docs as
text and reflect on the live runtime enums / secret registry / filesystem — no mocks, real layers.

The home for cross-cutting repo-level documentation tests; collected via ``testpaths`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

from lunaris_runtime.schema import AcquisitionMode

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
