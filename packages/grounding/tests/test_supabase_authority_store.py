"""SupabaseSourceAuthorityStore: the table read + row→model mapping, proven against a fake
supabase-py client (no live Postgres in CI). The SQL is exercised by the migration + `supabase db
lint`; this pins the Python ↔ table contract, including the degrade-on-bad-row guard."""

from lunaris_grounding import SourceAuthority, SupabaseSourceAuthorityStore
from lunaris_runtime.schema import AuthorityKind, SourceType, SubjectField, TrustTier


class _FakeResponse:
    def __init__(self, data: list[dict[str, object]], count: int | None = None) -> None:
        self.data = data
        self.count = count


class _FakeQuery:
    """Records the supabase-py builder chain; returns canned rows / a delete count on execute()."""

    def __init__(
        self, calls: list[tuple], rows: list[dict[str, object]], delete_count: int
    ) -> None:
        self._calls = calls
        self._rows = rows
        self._delete_count = delete_count
        self._mode: str | None = None

    def select(self, columns: str) -> "_FakeQuery":
        self._calls.append(("select", columns))
        self._mode = "select"
        return self

    def upsert(self, row: dict[str, object], *, on_conflict: str) -> "_FakeQuery":
        self._calls.append(("upsert", row, on_conflict))
        self._mode = "upsert"
        return self

    def delete(self, count: str | None = None) -> "_FakeQuery":
        self._calls.append(("delete", count))
        self._mode = "delete"
        return self

    def eq(self, column: str, value: object) -> "_FakeQuery":
        self._calls.append(("eq", column, value))
        return self

    def is_(self, column: str, value: object) -> "_FakeQuery":
        self._calls.append(("is_", column, value))
        return self

    def execute(self) -> _FakeResponse:
        if self._mode == "delete":
            return _FakeResponse([], count=self._delete_count)
        if self._mode == "select":
            return _FakeResponse(self._rows)
        return _FakeResponse([])


class _FakeClient:
    def __init__(self, rows: list[dict[str, object]], delete_count: int = 0) -> None:
        self.calls: list[tuple] = []
        self._rows = rows
        self._delete_count = delete_count

    def table(self, name: str) -> _FakeQuery:
        self.calls.append(("table", name))
        return _FakeQuery(self.calls, self._rows, self._delete_count)


async def test_list_all_maps_rows_to_authorities() -> None:
    # Arrange — a spine, a field pack, and a denylist row as the table would return them.
    rows = [
        {
            "domain": "en.wikipedia.org",
            "kind": "spine",
            "field": None,
            "tier": "reputable",
            "source_type": "reference",
            "note": None,
        },
        {
            "domain": "pubmed.ncbi.nlm.nih.gov",
            "kind": "pack",
            "field": "medicine",
            "tier": "official",
            "source_type": "database",
            "note": "evidence base",
        },
        {
            "domain": "bit.ly",
            "kind": "denylist",
            "field": None,
            "tier": "blocked",
            "source_type": None,
            "note": None,
        },
    ]
    store = SupabaseSourceAuthorityStore(client=_FakeClient(rows))

    # Act
    authorities = await store.list_all()

    # Assert — it queries the right table, and every row maps to a typed authority.
    assert ("table", "source_authorities") in store._client.calls  # type: ignore[attr-defined]
    selects = [c[1] for c in store._client.calls if c[0] == "select"]  # type: ignore[attr-defined]
    assert selects and "domain" in selects[0] and "note" in selects[0]
    assert {a.domain for a in authorities} == {
        "en.wikipedia.org",
        "pubmed.ncbi.nlm.nih.gov",
        "bit.ly",
    }
    pack = next(a for a in authorities if a.domain == "pubmed.ncbi.nlm.nih.gov")
    assert pack.kind is AuthorityKind.PACK
    assert pack.field is SubjectField.MEDICINE
    assert pack.trust_tier is TrustTier.OFFICIAL
    assert pack.source_type is SourceType.DATABASE
    spine = next(a for a in authorities if a.domain == "en.wikipedia.org")
    assert spine.kind is AuthorityKind.SPINE
    assert spine.field is None
    denylist = next(a for a in authorities if a.domain == "bit.ly")
    assert denylist.kind is AuthorityKind.DENYLIST
    assert denylist.trust_tier is TrustTier.BLOCKED
    assert denylist.field is None


async def test_list_all_drops_a_corrupt_row_instead_of_crashing() -> None:
    # Arrange — one good row, one with an out-of-vocab tier, one with a pack/field inconsistency.
    rows = [
        {"domain": "good.example", "kind": "spine", "field": None, "tier": "official"},
        {"domain": "bad-enum.example", "kind": "spine", "field": None, "tier": "platinum"},
        {"domain": "bad-shape.example", "kind": "pack", "field": None, "tier": "official"},
    ]
    store = SupabaseSourceAuthorityStore(client=_FakeClient(rows))

    # Act
    authorities = await store.list_all()

    # Assert — a malformed row degrades coverage (it is skipped), never the whole config read.
    assert [a.domain for a in authorities] == ["good.example"]


async def test_upsert_writes_the_row_with_the_conflict_key() -> None:
    # Arrange
    store = SupabaseSourceAuthorityStore(client=_FakeClient([]))
    authority = SourceAuthority(
        domain="pubmed.ncbi.nlm.nih.gov",
        kind=AuthorityKind.PACK,
        field=SubjectField.MEDICINE,
        trust_tier=TrustTier.OFFICIAL,
        source_type=SourceType.DATABASE,
    )

    # Act
    await store.upsert(authority)

    # Assert — upsert with the (domain, field) conflict key + enum values serialised to strings.
    calls = store._client.calls  # type: ignore[attr-defined]
    upserts = [c for c in calls if c[0] == "upsert"]
    assert len(upserts) == 1
    _, row, on_conflict = upserts[0]
    assert on_conflict == "domain,field"
    assert row["domain"] == "pubmed.ncbi.nlm.nih.gov"
    assert row["kind"] == "pack"
    assert row["field"] == "medicine"
    assert row["tier"] == "official"
    assert row["source_type"] == "database"


async def test_delete_a_global_row_filters_on_field_is_null() -> None:
    # Arrange — a global (field None) row deletes via IS NULL, not eq(None).
    store = SupabaseSourceAuthorityStore(client=_FakeClient([], delete_count=1))

    # Act
    removed = await store.delete("en.wikipedia.org", None)

    # Assert
    calls = store._client.calls  # type: ignore[attr-defined]
    assert ("eq", "domain", "en.wikipedia.org") in calls
    assert ("is_", "field", "null") in calls
    assert removed is True


async def test_delete_a_pack_row_filters_on_the_field_value() -> None:
    # Arrange — a field-scoped row deletes via eq on the field; nothing matched → False.
    store = SupabaseSourceAuthorityStore(client=_FakeClient([], delete_count=0))

    # Act
    removed = await store.delete("pubmed.ncbi.nlm.nih.gov", SubjectField.MEDICINE)

    # Assert
    calls = store._client.calls  # type: ignore[attr-defined]
    assert ("eq", "field", "medicine") in calls
    assert removed is False
