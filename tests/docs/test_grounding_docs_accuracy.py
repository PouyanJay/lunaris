"""Doc-accuracy tests for the P6 grounding documentation (the docs TDD steering wheel).

These tests pin the user-facing ``grounding-model.md`` to the live runtime so the docs cannot
silently drift from the code: enum members (``AcquisitionMode``, ``TrustTier``, ``SourceType``), the
HIGH-risk credibility floor constant, and the env vars the doc names as gating keys. No mocks — real
enum imports, real file reads.

The home for cross-cutting repo-level documentation tests; collected via ``testpaths`` in
``pyproject.toml``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lunaris_grounding.verifier import _HIGH_CREDIBILITY_FLOOR
from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GROUNDING_MODEL = _REPO_ROOT / "documentation" / "grounding-model.md"
_WALKTHROUGH = _REPO_ROOT / "documentation" / "build-a-course-walkthrough.md"
_README = _REPO_ROOT / "README.md"
_ENV_SAMPLE = _REPO_ROOT / ".env.sample"

# The docs that cross-link each other and the corpus story; their relative links must all resolve.
_LINKED_DOCS = [
    _GROUNDING_MODEL,
    _WALKTHROUGH,
    _README,
    _REPO_ROOT / "documentation" / "relevance-model.md",
]

# Matched against the doc so a documented key name that is absent from .env.sample is caught as a
# typo before it ships. Scoped to API-key and Supabase vars — the ones the grounding docs cite.
_ENV_VAR_PATTERN = re.compile(r"\b(?:[A-Z][A-Z0-9_]*_API_KEY|SUPABASE_[A-Z_]+)\b")

# A relative markdown link to another doc: the path inside ](…), skipping http(s) and pure anchors.
_RELATIVE_LINK_PATTERN = re.compile(r"\]\((?!https?:|#)([^)]+\.md)(?:#[^)]*)?\)")


def _require_doc(doc: Path) -> None:
    assert doc.exists(), f"expected documentation file is missing: {doc.relative_to(_REPO_ROOT)}"


def _read(doc: Path) -> str:
    _require_doc(doc)
    return doc.read_text(encoding="utf-8")


def _normalise(text: str) -> str:
    """Lowercase and collapse hyphens/underscores so 'peer-reviewed' matches 'peer_reviewed'."""
    return text.lower().replace("-", " ").replace("_", " ")


def _documents_term(normalised_text: str, term: str) -> bool:
    """True if `term` (already normalised) appears as a standalone word, not buried in a longer one.

    Word-boundary matching keeps a short value like ``seed`` or ``open`` from being satisfied by an
    unrelated mention inside another token, so the assertion proves the concept is actually covered.
    """
    return re.search(rf"\b{re.escape(term)}\b", normalised_text) is not None


def _env_sample_keys(env_sample_text: str) -> set[str]:
    """The variable names actually declared in .env.sample (``KEY=…`` lines, ignoring comments)."""
    return {
        line.split("=", 1)[0].strip()
        for line in env_sample_text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


@pytest.mark.parametrize(
    "enum_cls",
    [AcquisitionMode, TrustTier, SourceType],
    ids=["acquisition_mode", "trust_tier", "source_type"],
)
def test_grounding_model_documents_every_enum_member(enum_cls: type) -> None:
    # The trust tiers, source types, and acquisition modes are the spine of the model — the doc must
    # name each, or it describes a model the code no longer has.
    text = _normalise(_read(_GROUNDING_MODEL))

    missing = [m.value for m in enum_cls if not _documents_term(text, _normalise(m.value))]

    assert not missing, f"grounding-model.md omits {enum_cls.__name__} members: {missing}"


def test_grounding_model_states_the_high_risk_credibility_floor() -> None:
    # The documented floor must match the verifier's constant, or the doc lies about the moat.
    text = _read(_GROUNDING_MODEL)
    floor = f"{_HIGH_CREDIBILITY_FLOOR:.2f}"

    assert floor in text, f"grounding-model.md must state the HIGH-risk credibility floor ({floor})"


def test_grounding_model_env_vars_exist_in_env_sample() -> None:
    # Every env var the doc names as a key must be one that .env.sample actually declares.
    declared = _env_sample_keys(_read(_ENV_SAMPLE))
    documented = set(_ENV_VAR_PATTERN.findall(_read(_GROUNDING_MODEL)))

    unknown = sorted(var for var in documented if var not in declared)

    assert not unknown, f"grounding-model.md names env vars absent from .env.sample: {unknown}"


def test_grounding_model_names_the_free_scholarly_registry() -> None:
    # OpenAlex being free is a load-bearing honesty/cost point; it must be stated.
    text = _read(_GROUNDING_MODEL).lower()

    assert "openalex" in text, "grounding-model.md must name OpenAlex (the free scholarly registry)"


def test_grounding_model_documents_the_keys_that_gate_grounding() -> None:
    # The cost story is honest only if it names the keys that actually gate the corpus:
    # SEARCH_API_KEY (auto-discovery) and EMBEDDINGS_API_KEY (every ingest path embeds via Voyage).
    text = _read(_GROUNDING_MODEL)

    missing = [key for key in ("SEARCH_API_KEY", "EMBEDDINGS_API_KEY") if key not in text]

    assert not missing, f"grounding-model.md omits keys central to the cost story: {missing}"


@pytest.mark.parametrize("doc", _LINKED_DOCS, ids=lambda d: d.name)
def test_doc_relative_links_resolve(doc: Path) -> None:
    # A broken cross-link is the most common form of doc-rot; every relative .md link must resolve.
    targets = _RELATIVE_LINK_PATTERN.findall(_read(doc))

    broken = sorted(link for link in targets if not (doc.parent / link).resolve().exists())

    assert not broken, f"{doc.name} has unresolved relative links: {broken}"


def test_walkthrough_covers_filling_the_corpus() -> None:
    # P6 made grounding real: the walkthrough must show how to fill the corpus and link the model.
    text = _read(_WALKTHROUGH)
    lowered = text.lower()

    assert "corpus" in lowered, "the walkthrough must cover the Corpus tab / filling the corpus"
    assert "grounding-model.md" in text, "the walkthrough must link grounding-model.md"
