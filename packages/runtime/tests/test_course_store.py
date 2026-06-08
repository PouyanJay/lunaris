"""SupabaseCourseStore tests — the jsonb round-trip + query/column mapping, proven against a fake
client (no live Postgres in CI, mirroring test_run_store.py). The real-Postgres round-trip is
verified out of band during the journey, like the repo's live evals."""

import pytest
from lunaris_runtime.persistence import SupabaseCourseStore
from lunaris_runtime.schema import Course


class _FakeResponse:
    def __init__(
        self, data: list[dict[str, object]] | None = None, count: int | None = None
    ) -> None:
        self.data = data
        self.count = count


class _FakeQuery:
    """Records the supabase-py builder chain; returns canned rows (select) or a count (delete)."""

    def __init__(
        self, calls: list[tuple], select_data: list[dict[str, object]], delete_count: int
    ) -> None:
        self._calls = calls
        self._select_data = select_data
        self._delete_count = delete_count
        self._is_delete = False

    def upsert(self, row: dict[str, object]) -> "_FakeQuery":
        self._calls.append(("upsert", row))
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
            return _FakeResponse(count=self._delete_count)
        return _FakeResponse(data=self._select_data)


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


def _store_with(client: _FakeClient) -> SupabaseCourseStore:
    # Inject the fake via the public constructor seam — no creds, no network.
    return SupabaseCourseStore(client=client)


def test_save_upserts_the_course_as_camelcase_jsonb() -> None:
    # Arrange
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")
    client = _FakeClient()
    store = _store_with(client)

    # Act
    store.save(course)

    # Assert — an upsert into `courses` with the id, camelCase Course payload, status, updated_at.
    assert ("table", "courses") in client.calls
    upserts = [call[1] for call in client.calls if call[0] == "upsert"]
    assert len(upserts) == 1
    row = upserts[0]
    assert row["id"] == "abc"
    assert row["status"] == course.status.value
    assert "updated_at" in row
    # payload is the by-alias dump (camelCase keys), not the snake_case field names.
    assert row["payload"]["goalConcept"] == "kc-9"
    assert "goal_concept" not in row["payload"]


def test_load_round_trips_the_course_from_the_payload() -> None:
    # Arrange — a canned row holding the course's own by-alias dump (what the jsonb column returns).
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")
    payload = course.model_dump(by_alias=True, mode="json")
    client = _FakeClient(select_data=[{"payload": payload}])
    store = _store_with(client)

    # Act
    loaded = store.load("abc")

    # Assert — the Course round-trips equal, read from `courses` scoped to the id.
    assert loaded == course
    assert ("table", "courses") in client.calls
    assert ("eq", "id", "abc") in client.calls


def test_load_raises_not_found_when_absent() -> None:
    # Arrange — no rows.
    store = _store_with(_FakeClient(select_data=[]))

    # Act / Assert — the store-agnostic not-found signal the API service catches (parity with the
    # file store, which raises FileNotFoundError when the file is missing).
    with pytest.raises(FileNotFoundError):
        store.load("ghost")


def test_save_then_load_round_trips_through_the_payload() -> None:
    # Arrange — save into one fake (capturing the upserted payload), then load it back via another.
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")
    saver = _FakeClient()
    _store_with(saver).save(course)
    upserted_payload = next(call[1] for call in saver.calls if call[0] == "upsert")["payload"]

    # Act — the load reads exactly what save wrote (proves the save dump ↔ load validate agree).
    loaded = _store_with(_FakeClient(select_data=[{"payload": upserted_payload}])).load("abc")

    # Assert
    assert loaded == course


def test_delete_returns_true_when_a_row_was_removed() -> None:
    # Arrange — an exact-count delete that removed one row.
    client = _FakeClient(delete_count=1)
    store = _store_with(client)

    # Act
    removed = store.delete("abc")

    # Assert — a count="exact" delete on `courses` scoped to the id; True because a row was removed.
    assert removed is True
    assert ("table", "courses") in client.calls
    assert ("delete", "exact") in client.calls
    assert ("eq", "id", "abc") in client.calls


def test_delete_returns_false_when_no_row_exists() -> None:
    # Arrange — nothing matched the id.
    store = _store_with(_FakeClient(delete_count=0))

    # Act / Assert — idempotent: a no-op delete reports False (caller answers 404, not 204).
    assert store.delete("ghost") is False


# --- per-user scoping (Phase 2): the owner is stamped on write, filtered on read/delete ---------


def test_save_stamps_the_owner_when_scoped() -> None:
    # Arrange
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")
    client = _FakeClient()
    store = _store_with(client)

    # Act
    store.save(course, owner_id="user-7")

    # Assert — the upserted row carries user_id, so RLS enforces for any later user-JWT client.
    upserts = [call[1] for call in client.calls if call[0] == "upsert"]
    assert upserts[0]["user_id"] == "user-7"


def test_save_omits_user_id_when_unscoped() -> None:
    # Arrange
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")
    client = _FakeClient()

    # Act — auth off (owner_id None) leaves the row owner-less (today's behavior).
    _store_with(client).save(course)

    # Assert
    upserts = [call[1] for call in client.calls if call[0] == "upsert"]
    assert "user_id" not in upserts[0]


def test_load_filters_by_owner_when_scoped() -> None:
    # Arrange
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")
    payload = course.model_dump(by_alias=True, mode="json")
    client = _FakeClient(select_data=[{"payload": payload}])
    store = _store_with(client)

    # Act
    store.load("abc", owner_id="user-7")

    # Assert — the read is constrained to both the id and the owner.
    assert ("eq", "id", "abc") in client.calls
    assert ("eq", "user_id", "user-7") in client.calls


def test_delete_filters_by_owner_when_scoped() -> None:
    # Arrange
    client = _FakeClient(delete_count=1)
    store = _store_with(client)

    # Act
    store.delete("abc", owner_id="user-7")

    # Assert — only the owner's row can be deleted.
    assert ("eq", "user_id", "user-7") in client.calls
