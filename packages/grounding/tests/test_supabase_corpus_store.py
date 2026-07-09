"""SupabaseCorpusStore: the trust/provenance column write + the match RPC's filter/mapping shape,
proven against a fake supabase-py client (no live Postgres in CI). The SQL is exercised by the
migration + `supabase db lint`; this pins the Python ↔ RPC contract."""

import pytest
from lunaris_grounding import GroundingDocument, SupabaseCorpusStore
from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier


class _FakeResponse:
    def __init__(self, data: list[dict[str, object]], count: int | None = None) -> None:
        self.data = data
        self.count = count


class _FakeQuery:
    """Records the supabase-py builder chain and returns canned rows/count on execute()."""

    def __init__(
        self,
        calls: list[tuple],
        *,
        select_data: list[dict[str, object]] | None = None,
        rpc_data: list[dict[str, object]] | None = None,
        delete_count: int = 0,
        mode: str | None = None,
    ) -> None:
        self._calls = calls
        self._select_data = select_data or []
        self._rpc_data = rpc_data or []
        self._delete_count = delete_count
        self._mode = mode

    def upsert(self, rows: list[dict[str, object]]) -> "_FakeQuery":
        self._calls.append(("upsert", rows))
        self._mode = "upsert"
        return self

    def select(self, columns: str) -> "_FakeQuery":
        self._calls.append(("select", columns))
        self._mode = "select"
        return self

    def delete(self, count: str | None = None) -> "_FakeQuery":
        self._calls.append(("delete", count))
        self._mode = "delete"
        return self

    def eq(self, column: str, value: object) -> "_FakeQuery":
        self._calls.append(("eq", column, value))
        return self

    def execute(self) -> _FakeResponse:
        if self._mode == "rpc":
            return _FakeResponse(self._rpc_data)
        if self._mode == "delete":
            return _FakeResponse([], count=self._delete_count)
        if self._mode == "select":
            return _FakeResponse(self._select_data)
        return _FakeResponse([])


class _FakeClient:
    def __init__(
        self,
        *,
        rpc_data: list[dict[str, object]] | None = None,
        table_rows: list[dict[str, object]] | None = None,
        delete_count: int = 0,
    ) -> None:
        self.calls: list[tuple] = []
        self._rpc_data = rpc_data or []
        self._table_rows = table_rows or []
        self._delete_count = delete_count

    def table(self, name: str) -> _FakeQuery:
        self.calls.append(("table", name))
        return _FakeQuery(self.calls, select_data=self._table_rows, delete_count=self._delete_count)

    def rpc(self, fn: str, params: dict[str, object]) -> _FakeQuery:
        self.calls.append(("rpc", fn, params))
        return _FakeQuery(self.calls, rpc_data=self._rpc_data, mode="rpc")


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
        source_id="src-abc",
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
    # source_id MUST be written or the durable list/delete surface is silently dead.
    assert rows[0]["source_id"] == "src-abc"


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


def _source_chunk(source_id: str, **overrides: object) -> dict[str, object]:
    """A grounding_documents row as the source-list select returns it. url/source_type/credibility
    default to None — a manual pasted source has no origin URL or computed credibility yet."""
    row: dict[str, object] = {
        "source_id": source_id,
        "course_id": "course-1",
        "title": "Dijkstra notes",
        "url": None,
        "source_type": None,
        "trust_tier": "vouched",
        "credibility": None,
        "acquisition_mode": "manual",
        "fetched_at": "2026-06-04T00:00:00Z",
    }
    row.update(overrides)
    return row


async def test_supabase_list_sources_folds_rows_by_source_scoped_to_the_course() -> None:
    # Arrange — two chunks of source s1 + one of s2 (as the course-scoped select returns them).
    client = _FakeClient(table_rows=[_source_chunk("s1"), _source_chunk("s1"), _source_chunk("s2")])
    store = _store_with(client)

    # Act
    sources = await store.list_sources_for_course("course-1")

    # Assert — the select reads grounding_documents filtered by course_id, and rows fold into one
    # summary per source_id (carrying the chunk's provenance + a count).
    assert ("table", "grounding_documents") in client.calls
    assert ("eq", "course_id", "course-1") in client.calls
    # The select must NOT pull the chunk content/embedding into a list response (large blobs).
    selects = [c[1] for c in client.calls if c[0] == "select"]
    assert selects and all("content" not in cols and "embedding" not in cols for cols in selects)
    by_id = {s.source_id: s for s in sources}
    assert set(by_id) == {"s1", "s2"}
    assert by_id["s1"].chunk_count == 2
    assert by_id["s2"].chunk_count == 1
    assert by_id["s1"].trust_tier is TrustTier.VOUCHED
    assert by_id["s1"].acquisition_mode is AcquisitionMode.MANUAL


async def test_supabase_list_sources_degrades_on_a_corrupt_trust_value() -> None:
    # Arrange — a stored chunk with an out-of-vocab trust_tier must not crash the list.
    client = _FakeClient(table_rows=[_source_chunk("s1", trust_tier="bogus")])
    store = _store_with(client)

    # Act
    [summary] = await store.list_sources_for_course("course-1")

    # Assert — the source still lists, with the bad tier degraded to None.
    assert summary.source_id == "s1"
    assert summary.trust_tier is None


async def test_supabase_delete_source_targets_source_id_and_returns_count() -> None:
    # Arrange — the DB reports two chunks removed for the source.
    client = _FakeClient(delete_count=2)
    store = _store_with(client)

    # Act
    removed = await store.delete_source("s1")

    # Assert — a DELETE on grounding_documents scoped to source_id, with an exact count requested.
    assert removed == 2
    assert ("table", "grounding_documents") in client.calls
    assert ("delete", "exact") in client.calls
    assert ("eq", "source_id", "s1") in client.calls


async def test_supabase_delete_for_course_scopes_by_course_id_and_returns_count() -> None:
    # Arrange — the DB reports three chunks removed for the course (incl. any source-less ones).
    client = _FakeClient(delete_count=3)
    store = _store_with(client)

    # Act — the full-course-delete grounding arm (course-scoped: the table has no owner column).
    removed = await store.delete_for_course("course-1")

    # Assert — a DELETE on grounding_documents scoped to course_id ONLY, with an exact count.
    assert removed == 3
    assert ("table", "grounding_documents") in client.calls
    assert ("delete", "exact") in client.calls
    assert ("eq", "course_id", "course-1") in client.calls
    assert not any(call[:2] == ("eq", "user_id") for call in client.calls)
