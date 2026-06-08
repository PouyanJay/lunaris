"""Tests for the BYOK credential store (Phase 2, T4) — per-user encrypted provider keys.

The store persists ciphertext only (the SecretCipher does the crypto a layer up); it never sees a
plaintext key. Two backends: the in-memory fallback (CRUD + per-user isolation, proven functionally)
and the Supabase store (column/filter mapping, proven against a fake client — no live Postgres).
"""

import base64

from lunaris_api.secrets import (
    BYOK_PROVIDERS,
    EncryptedSecret,
    InMemoryCredentialStore,
    SupabaseCredentialStore,
)


def _enc(tag: str) -> EncryptedSecret:
    return EncryptedSecret(nonce=f"nonce-{tag}".encode(), ciphertext=f"cipher-{tag}".encode())


# --- InMemoryCredentialStore: functional CRUD + per-user isolation ------------------------------


async def test_set_then_get_round_trips_the_ciphertext() -> None:
    # Arrange
    store = InMemoryCredentialStore()
    secret = _enc("a")

    # Act
    await store.set(user_id="u-1", provider="anthropic", secret=secret, last4="9abc")
    got = await store.get(user_id="u-1", provider="anthropic")

    # Assert — the exact encrypted blob comes back (the cipher decrypts it elsewhere).
    assert got == secret


async def test_get_missing_credential_is_none() -> None:
    # Arrange
    store = InMemoryCredentialStore()

    # Act / Assert
    assert await store.get(user_id="u-1", provider="search") is None


async def test_set_overwrites_an_existing_provider_key() -> None:
    # Arrange
    store = InMemoryCredentialStore()
    await store.set(user_id="u-1", provider="anthropic", secret=_enc("old"), last4="0000")

    # Act — rotating the key replaces the row (one credential per provider per user).
    await store.set(user_id="u-1", provider="anthropic", secret=_enc("new"), last4="1111")

    # Assert
    assert await store.get(user_id="u-1", provider="anthropic") == _enc("new")


async def test_statuses_reports_every_provider_with_set_state() -> None:
    # Arrange — one provider set, the rest unset.
    store = InMemoryCredentialStore()
    await store.set(user_id="u-1", provider="anthropic", secret=_enc("a"), last4="9abc")

    # Act
    statuses = await store.statuses(user_id="u-1")

    # Assert — every BYOK provider is listed; only anthropic is set, with its last4 (never a value).
    by_provider = {s.provider: s for s in statuses}
    assert set(by_provider) == set(BYOK_PROVIDERS)
    assert by_provider["anthropic"].is_set is True
    assert by_provider["anthropic"].last4 == "9abc"
    assert by_provider["search"].is_set is False
    assert by_provider["search"].last4 is None


async def test_credentials_are_isolated_per_user() -> None:
    # Arrange — A sets a key; B sets nothing.
    store = InMemoryCredentialStore()
    await store.set(user_id="u-a", provider="anthropic", secret=_enc("a"), last4="aaaa")

    # Act / Assert — B can't read A's key, and B's status shows nothing set.
    assert await store.get(user_id="u-b", provider="anthropic") is None
    assert all(not s.is_set for s in await store.statuses(user_id="u-b"))


async def test_delete_is_owner_scoped_and_idempotent() -> None:
    # Arrange
    store = InMemoryCredentialStore()
    await store.set(user_id="u-a", provider="anthropic", secret=_enc("a"), last4="aaaa")

    # Act / Assert — B can't delete A's key; A can; a second delete is a no-op.
    assert await store.delete(user_id="u-b", provider="anthropic") is False
    assert await store.delete(user_id="u-a", provider="anthropic") is True
    assert await store.delete(user_id="u-a", provider="anthropic") is False
    assert await store.get(user_id="u-a", provider="anthropic") is None


# --- SupabaseCredentialStore: column mapping + query shape, proven without a live DB -------------


class _FakeResponse:
    def __init__(self, data: list[dict[str, object]], count: int | None = None) -> None:
        self.data = data
        self.count = count


class _FakeQuery:
    """Records the supabase-py builder chain and returns canned rows / counts on execute()."""

    def __init__(
        self, calls: list[tuple], select_data: list[dict[str, object]], delete_count: int
    ) -> None:
        self._calls = calls
        self._select_data = select_data
        self._delete_count = delete_count
        self._is_delete = False

    def upsert(self, row: dict[str, object], on_conflict: str | None = None) -> "_FakeQuery":
        self._calls.append(("upsert", row, on_conflict))
        return self

    def select(self, columns: str) -> "_FakeQuery":
        self._calls.append(("select", columns))
        return self

    def delete(self, count: str | None = None) -> "_FakeQuery":
        self._is_delete = True
        self._calls.append(("delete", count))
        return self

    def eq(self, column: str, value: object) -> "_FakeQuery":
        self._calls.append(("eq", column, value))
        return self

    def limit(self, count: int) -> "_FakeQuery":
        self._calls.append(("limit", count))
        return self

    def execute(self) -> _FakeResponse:
        if self._is_delete:
            return _FakeResponse([], count=self._delete_count)
        return _FakeResponse(self._select_data)


class _FakeClient:
    def __init__(
        self, select_data: list[dict[str, object]] | None = None, delete_count: int = 0
    ) -> None:
        self.calls: list[tuple] = []
        self._select_data = select_data or []
        self._delete_count = delete_count

    def table(self, name: str) -> _FakeQuery:
        self.calls.append(("table", name))
        return _FakeQuery(self.calls, self._select_data, self._delete_count)


def _store_with(client: _FakeClient) -> SupabaseCredentialStore:
    return SupabaseCredentialStore(client=client)


async def test_supabase_set_upserts_base64_ciphertext_scoped_to_user_and_provider() -> None:
    # Arrange
    client = _FakeClient()
    store = _store_with(client)
    secret = EncryptedSecret(nonce=b"\x00\x01\x02", ciphertext=b"\xaa\xbb\xcc")

    # Act
    await store.set(user_id="u-1", provider="anthropic", secret=secret, last4="9abc")

    # Assert — one upsert into provider_credentials: user_id + provider + base64 blobs + last4.
    assert ("table", "provider_credentials") in client.calls
    upsert = next(call for call in client.calls if call[0] == "upsert")
    row = upsert[1]
    assert row["user_id"] == "u-1"
    assert row["provider"] == "anthropic"
    assert row["last4"] == "9abc"
    # Binary is stored as base64 text (avoids PostgREST bytea hex friction); decodes to the bytes.
    assert base64.b64decode(row["ciphertext"]) == b"\xaa\xbb\xcc"
    assert base64.b64decode(row["nonce"]) == b"\x00\x01\x02"
    # The composite-PK conflict target makes a re-set ROTATE the key in place (no duplicate row).
    assert upsert[2] == "user_id,provider"


async def test_supabase_set_writes_the_callers_user_id() -> None:
    # Arrange — two stores, two users, same provider (guards against a cached/stale user_id).
    secret = EncryptedSecret(nonce=b"\x00", ciphertext=b"\x01")
    client_a, client_b = _FakeClient(), _FakeClient()

    # Act
    await _store_with(client_a).set(
        user_id="u-a", provider="anthropic", secret=secret, last4="aaaa"
    )
    await _store_with(client_b).set(
        user_id="u-b", provider="anthropic", secret=secret, last4="bbbb"
    )

    # Assert — each upsert carries its own caller's user_id, never the other's.
    row_a = next(call[1] for call in client_a.calls if call[0] == "upsert")
    row_b = next(call[1] for call in client_b.calls if call[0] == "upsert")
    assert row_a["user_id"] == "u-a"
    assert row_b["user_id"] == "u-b"


async def test_supabase_get_decodes_the_blob_scoped_to_user_and_provider() -> None:
    # Arrange — a canned row with base64-encoded columns.
    rows = [
        {
            "ciphertext": base64.b64encode(b"\xaa\xbb").decode(),
            "nonce": base64.b64encode(b"\x00\x01").decode(),
        }
    ]
    client = _FakeClient(select_data=rows)
    store = _store_with(client)

    # Act
    got = await store.get(user_id="u-1", provider="anthropic")

    # Assert — decoded back to bytes; read scoped to both user_id and provider.
    assert got == EncryptedSecret(nonce=b"\x00\x01", ciphertext=b"\xaa\xbb")
    assert ("eq", "user_id", "u-1") in client.calls
    assert ("eq", "provider", "anthropic") in client.calls


async def test_supabase_get_missing_is_none() -> None:
    # Arrange
    store = _store_with(_FakeClient(select_data=[]))

    # Act / Assert
    assert await store.get(user_id="u-1", provider="anthropic") is None


async def test_supabase_statuses_lists_all_providers_from_the_users_rows() -> None:
    # Arrange — the user has one stored key.
    rows = [{"provider": "anthropic", "last4": "9abc"}]
    client = _FakeClient(select_data=rows)
    store = _store_with(client)

    # Act
    statuses = await store.statuses(user_id="u-1")

    # Assert — read scoped to the user; every provider listed; only the stored one is set.
    assert ("eq", "user_id", "u-1") in client.calls
    by_provider = {s.provider: s for s in statuses}
    assert set(by_provider) == set(BYOK_PROVIDERS)
    assert by_provider["anthropic"].is_set is True
    assert by_provider["anthropic"].last4 == "9abc"
    assert by_provider["youtube"].is_set is False


async def test_supabase_statuses_treats_a_null_last4_row_as_set() -> None:
    # Arrange — a stored credential whose key was <4 chars, so last4 is null in the DB.
    client = _FakeClient(select_data=[{"provider": "search", "last4": None}])
    store = _store_with(client)

    # Act
    statuses = {s.provider: s for s in await store.statuses(user_id="u-1")}

    # Assert — presence of the row means set, independent of last4 (the credential exists).
    assert statuses["search"].is_set is True
    assert statuses["search"].last4 is None


async def test_supabase_delete_scoped_to_user_and_provider_returns_count() -> None:
    # Arrange
    client = _FakeClient(delete_count=1)
    store = _store_with(client)

    # Act
    removed = await store.delete(user_id="u-1", provider="anthropic")

    # Assert — an exact-count delete scoped to both keys.
    assert removed is True
    assert ("delete", "exact") in client.calls
    assert ("eq", "user_id", "u-1") in client.calls
    assert ("eq", "provider", "anthropic") in client.calls
