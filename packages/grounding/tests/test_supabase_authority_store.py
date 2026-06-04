"""SupabaseSourceAuthorityStore: the table read + row→model mapping, proven against a fake
supabase-py client (no live Postgres in CI). The SQL is exercised by the migration + `supabase db
lint`; this pins the Python ↔ table contract, including the degrade-on-bad-row guard."""

from lunaris_grounding import SupabaseSourceAuthorityStore
from lunaris_runtime.schema import AuthorityKind, SourceType, SubjectField, TrustTier


class _FakeResponse:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, calls: list[tuple], rows: list[dict[str, object]]) -> None:
        self._calls = calls
        self._rows = rows

    def select(self, columns: str) -> "_FakeQuery":
        self._calls.append(("select", columns))
        return self

    def execute(self) -> _FakeResponse:
        return _FakeResponse(self._rows)


class _FakeClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.calls: list[tuple] = []
        self._rows = rows

    def table(self, name: str) -> _FakeQuery:
        self.calls.append(("table", name))
        return _FakeQuery(self.calls, self._rows)


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
