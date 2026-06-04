"""SupabaseCorpusStore: the trust/provenance column write + the match RPC's filter/mapping shape,
proven against a fake supabase-py client (no live Postgres in CI). The SQL is exercised by the
migration + `supabase db lint`; this pins the Python ↔ RPC contract."""

import pytest
from lunaris_grounding import GroundingDocument, SupabaseCorpusStore
from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier


class _FakeResponse:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data


class _FakeQuery:
    """Records the supabase-py builder chain and returns canned rows on execute()."""

    def __init__(self, calls: list[tuple], rpc_data: list[dict[str, object]]) -> None:
        self._calls = calls
        self._rpc_data = rpc_data
        self._is_rpc = False

    def upsert(self, rows: list[dict[str, object]]) -> "_FakeQuery":
        self._calls.append(("upsert", rows))
        return self

    def execute(self) -> _FakeResponse:
        return _FakeResponse(self._rpc_data if self._is_rpc else [])


class _FakeClient:
    def __init__(self, rpc_data: list[dict[str, object]] | None = None) -> None:
        self.calls: list[tuple] = []
        self._rpc_data = rpc_data or []

    def table(self, name: str) -> _FakeQuery:
        self.calls.append(("table", name))
        return _FakeQuery(self.calls, [])

    def rpc(self, fn: str, params: dict[str, object]) -> _FakeQuery:
        self.calls.append(("rpc", fn, params))
        query = _FakeQuery(self.calls, self._rpc_data)
        query._is_rpc = True
        return query


def _store_with(client: _FakeClient) -> SupabaseCorpusStore:
    # Inject the fake via the public constructor seam — no creds, no network, no private reach-in.
    return SupabaseCorpusStore(client=client)


def _rpc_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "d1",
        "kc_id": "kc1",
        "content": "Dijkstra relaxes edges.",
        "title": "Algorithms",
        "url": "https://en.wikipedia.org/wiki/Dijkstra",
        "source_type": "reference",
        "trust_tier": "reputable",
        "credibility": 0.91,
        "fetched_at": "2026-06-03T00:00:00Z",
        "similarity": 0.9,
    }
    row.update(overrides)
    return row


async def test_supabase_upsert_writes_the_trust_provenance_columns() -> None:
    # Arrange
    client = _FakeClient()
    store = _store_with(client)
    document = GroundingDocument(
        id="d1",
        kc_id="kc1",
        content="c",
        embedding=(0.1, 0.2),
        title="T",
        url="https://example.edu/x",
        source_type=SourceType.REFERENCE,
        trust_tier=TrustTier.REPUTABLE,
        credibility=0.91,
        fetched_at="2026-06-03T00:00:00Z",
        acquisition_mode=AcquisitionMode.SEED,
        course_id="course-1",
    )

    # Act
    written = await store.upsert([document])

    # Assert — one upsert into grounding_documents carrying the trust/provenance columns, enums
    # serialised to their string .value (the columns are plain text, not jsonb).
    assert written == 1
    assert ("table", "grounding_documents") in client.calls
    [rows] = [call[1] for call in client.calls if call[0] == "upsert"]
    assert rows[0]["source_type"] == "reference"
    assert rows[0]["trust_tier"] == "reputable"
    assert rows[0]["credibility"] == 0.91
    assert rows[0]["fetched_at"] == "2026-06-03T00:00:00Z"
    assert rows[0]["acquisition_mode"] == "seed"
    assert rows[0]["course_id"] == "course-1"


async def test_supabase_match_passes_course_filter_and_maps_trust_columns() -> None:
    # Arrange — a canned RPC row carrying the trust columns.
    client = _FakeClient(rpc_data=[_rpc_row()])
    store = _store_with(client)

    # Act — scoped to a course + a KC.
    [evidence] = await store.match([1.0, 0.0], k=3, kc_id="kc1", course_id="course-1")

    # Assert — the RPC was called with the mandatory query + both filters, and the trust columns map
    # onto the citation (with the similarity becoming the evidence score).
    [rpc_call] = [c for c in client.calls if c[0] == "rpc"]
    assert rpc_call[1] == "match_grounding_documents"
    assert rpc_call[2]["query_embedding"] == [1.0, 0.0]
    assert rpc_call[2]["match_count"] == 3
    assert rpc_call[2]["kc_filter"] == "kc1"
    assert rpc_call[2]["course_filter"] == "course-1"
    assert evidence.score == pytest.approx(0.9)
    citation = evidence.citation
    assert citation.trust_tier is TrustTier.REPUTABLE
    assert citation.credibility == 0.91
    assert citation.source_type is SourceType.REFERENCE
    assert citation.fetched_at == "2026-06-03T00:00:00Z"


async def test_supabase_match_omits_filters_when_unscoped() -> None:
    # Arrange — the legacy/no-scope path keeps the params minimal so it resolves against the RPC's
    # defaulted filters (and would resolve against the pre-P6.0 signature too).
    client = _FakeClient(rpc_data=[_rpc_row()])
    store = _store_with(client)

    # Act
    await store.match([1.0, 0.0])

    # Assert — the same RPC, just without the optional scope params.
    [rpc_call] = [c for c in client.calls if c[0] == "rpc"]
    assert rpc_call[1] == "match_grounding_documents"
    assert "kc_filter" not in rpc_call[2]
    assert "course_filter" not in rpc_call[2]


async def test_supabase_match_degrades_on_a_corrupt_trust_value() -> None:
    # Arrange — a row whose trust_tier holds an out-of-vocabulary value (a corrupt / out-of-band DB
    # write). A malformed trust field must not crash the whole retrieval.
    client = _FakeClient(rpc_data=[_rpc_row(trust_tier="not-a-real-tier")])
    store = _store_with(client)

    # Act
    [evidence] = await store.match([1.0, 0.0], course_id="course-1")

    # Assert — the citation still comes back (coverage degraded, not failed): the bad trust field
    # drops to None, the rest of the citation survives.
    assert evidence.citation.id == "d1"
    assert evidence.citation.trust_tier is None
    assert evidence.citation.snippet == "Dijkstra relaxes edges."
