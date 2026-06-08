"""SupabaseUserConfigStore column mapping + query shape, proven without a live DB (fake client)."""

from lunaris_api.user_config import SupabaseUserConfigStore

_USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _FakeResponse:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, calls: list[tuple], select_data: list[dict[str, object]]) -> None:
        self._calls = calls
        self._select_data = select_data
        self._eq: dict[str, object] = {}

    def upsert(self, row: dict[str, object], on_conflict: str | None = None) -> "_FakeQuery":
        self._calls.append(("upsert", row, on_conflict))
        return self

    def select(self, columns: str) -> "_FakeQuery":
        self._calls.append(("select", columns))
        return self

    def eq(self, column: str, value: object) -> "_FakeQuery":
        self._eq[column] = value
        self._calls.append(("eq", column, value))
        return self

    def execute(self) -> _FakeResponse:
        return _FakeResponse(self._select_data)


class _FakeClient:
    def __init__(self, select_data: list[dict[str, object]] | None = None) -> None:
        self.calls: list[tuple] = []
        self._select_data = select_data or []

    def table(self, name: str) -> _FakeQuery:
        self.calls.append(("table", name))
        return _FakeQuery(self.calls, self._select_data)


async def test_set_upserts_scoped_to_user_and_key() -> None:
    # Arrange
    client = _FakeClient()
    store = SupabaseUserConfigStore(client=client)

    # Act
    await store.set(user_id=_USER_A, key="modelStrong", value="claude-opus-4-8")

    # Assert — one upsert into user_runtime_config on the composite PK with the caller's user_id.
    upsert = next(call for call in client.calls if call[0] == "upsert")
    row = upsert[1]
    assert (row["user_id"], row["config_key"], row["config_value"]) == (
        _USER_A,
        "modelStrong",
        "claude-opus-4-8",
    )
    assert upsert[2] == "user_id,config_key"
    assert ("table", "user_runtime_config") in client.calls


async def test_get_all_maps_rows_to_key_value() -> None:
    # Arrange — the user has two rows.
    rows = [
        {"config_key": "modelStrong", "config_value": "strong-x"},
        {"config_key": "modelWorker", "config_value": "worker-y"},
    ]
    store = SupabaseUserConfigStore(client=_FakeClient(select_data=rows))

    # Act
    result = await store.get_all(user_id=_USER_A)

    # Assert
    assert result == {"modelStrong": "strong-x", "modelWorker": "worker-y"}


async def test_get_all_filters_by_user_id() -> None:
    client = _FakeClient(select_data=[])
    store = SupabaseUserConfigStore(client=client)

    await store.get_all(user_id=_USER_A)

    assert ("eq", "user_id", _USER_A) in client.calls


async def test_get_all_empty_is_empty_dict() -> None:
    store = SupabaseUserConfigStore(client=_FakeClient(select_data=[]))

    assert await store.get_all(user_id=_USER_A) == {}
