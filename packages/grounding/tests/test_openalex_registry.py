"""The live OpenAlex scholarly registry (P6.3): resolve a source URL to its peer-reviewed record.

Exercised with an injected fake HTTP client (no network), so the DOI extraction, the OpenAlex
response mapping, the preprint exclusion, and the best-effort degradation are all deterministic.
"""

from typing import Any

import pytest
from lunaris_grounding import (
    CandidateSource,
    CredibilityScorer,
    InMemorySourceAuthorityStore,
    OpenAlexScholarlyRegistry,
    ScholarlyRecord,
)
from lunaris_runtime.schema import TrustTier


class _FakeResponse:
    """The slice of an HTTP response the registry uses; raises on a non-OK status when asked."""

    def __init__(self, payload: object, *, ok: bool = True) -> None:
        self._payload = payload
        self._ok = ok

    def raise_for_status(self) -> None:
        if not self._ok:
            raise RuntimeError("simulated HTTP error")

    def json(self) -> object:
        return self._payload


class _FakeClient:
    """Records the GETs it receives and returns a canned response (or raises a transport error)."""

    def __init__(self, response: _FakeResponse | None = None, *, raises: bool = False) -> None:
        self._response = response
        self._raises = raises
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def get(self, url: str, *, params: dict[str, str]) -> _FakeResponse:
        self.calls.append((url, params))
        if self._raises:
            raise RuntimeError("simulated transport failure")
        if self._response is None:
            raise ValueError("_FakeClient misconfigured: provide a response or set raises=True")
        return self._response


def _work(*, source_type: str = "journal", cited_by: int = 42) -> dict[str, Any]:
    """A minimal OpenAlex work payload with the fields the registry reads."""
    return {
        "doi": "https://doi.org/10.7717/peerj.4375",
        "cited_by_count": cited_by,
        "primary_location": {"source": {"display_name": "PeerJ", "type": source_type}},
    }


async def test_resolves_a_doi_url_to_its_scholarly_record() -> None:
    # Arrange — a journal-article work behind a DOI URL.
    client = _FakeClient(_FakeResponse(_work()))
    registry = OpenAlexScholarlyRegistry(mailto="dev@example.org", client=client)

    # Act
    record = await registry.lookup("https://doi.org/10.7717/peerj.4375")

    # Assert — the venue, DOI, and citation count are carried onto the record.
    assert record == ScholarlyRecord(venue="PeerJ", doi="10.7717/peerj.4375", citation_count=42)
    # The DOI was looked up by id, and the polite-pool mailto rode along.
    (url, params) = client.calls[0]
    assert "10.7717/peerj.4375" in url
    assert params.get("mailto") == "dev@example.org"


async def test_extracts_a_doi_embedded_in_a_publisher_url() -> None:
    # Arrange — a publisher landing page whose path contains the DOI.
    client = _FakeClient(_FakeResponse(_work()))
    registry = OpenAlexScholarlyRegistry(client=client)

    # Act
    record = await registry.lookup("https://dl.acm.org/doi/10.7717/peerj.4375")

    # Assert — the embedded DOI is found, looked up, and parsed into the full record.
    assert record == ScholarlyRecord(venue="PeerJ", doi="10.7717/peerj.4375", citation_count=42)
    assert "10.7717/peerj.4375" in client.calls[0][0]


async def test_a_url_with_no_doi_returns_none_without_a_request() -> None:
    # Arrange — an open-web page with no DOI anywhere in it.
    client = _FakeClient(_FakeResponse(_work()))
    registry = OpenAlexScholarlyRegistry(client=client)

    # Act
    record = await registry.lookup("https://example.com/blog/sorting-explained")

    # Assert — no DOI → no record, and no needless network call.
    assert record is None
    assert client.calls == []


async def test_a_preprint_repository_does_not_resolve_to_a_peer_reviewed_record() -> None:
    # Arrange — a DOI that OpenAlex hosts on a repository (a preprint server), not a journal.
    client = _FakeClient(_FakeResponse(_work(source_type="repository")))
    registry = OpenAlexScholarlyRegistry(client=client)

    # Act
    record = await registry.lookup("https://doi.org/10.7717/peerj.4375")

    # Assert — preprints are sub-REPUTABLE (plan §4a): no record floors their tier.
    assert record is None


async def test_a_transport_error_degrades_to_none() -> None:
    # Arrange — the OpenAlex call fails (timeout / 5xx / unreachable).
    client = _FakeClient(raises=True)
    registry = OpenAlexScholarlyRegistry(client=client)

    # Act
    record = await registry.lookup("https://doi.org/10.7717/peerj.4375")

    # Assert — best-effort: a failed lookup never raises, it just resolves nothing.
    assert record is None


async def test_a_404_for_an_unindexed_doi_degrades_to_none() -> None:
    # Arrange — a syntactically valid DOI that OpenAlex does not index (raise_for_status raises).
    client = _FakeClient(_FakeResponse(None, ok=False))
    registry = OpenAlexScholarlyRegistry(client=client)

    # Act
    record = await registry.lookup("https://doi.org/10.9999/not-a-real-doi")

    # Assert
    assert record is None


async def test_the_registry_floors_an_unknown_open_domain_to_reputable_through_the_scorer() -> None:
    # Arrange — the real OpenAlex registry (fake HTTP) wired into the credibility scorer, scoring an
    # unknown open-web domain whose URL carries a DOI OpenAlex confirms is a journal article. The
    # seam P6.2 left for P6.3: a machine-found paper on an unknown host is graded, not dismissed.
    registry = OpenAlexScholarlyRegistry(client=_FakeClient(_FakeResponse(_work())))
    scorer = CredibilityScorer(InMemorySourceAuthorityStore(), registry=registry)
    source = CandidateSource(
        kc_id="kc1",
        text=" ".join(f"concept{i} explained clearly" for i in range(60)),
        url="https://unknown-journal.example/article/10.7717/peerj.4375",
    )

    # Act
    scored = await scorer.score(source)

    # Assert — the OpenAlex-confirmed record floors the unknown host to REPUTABLE.
    assert scored.trust_tier is TrustTier.REPUTABLE
    assert scored.credibility == pytest.approx(0.75)
