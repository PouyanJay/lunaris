"""Unit coverage for SupabaseProgressStore's PostgREST payload shapes — the one contract the
live-SQL suite can't see: ``touch_course`` must OMIT ``last_lesson_id`` from the upsert payload
on a bare touch (PostgREST's conflict-update only SETs payload columns, so omission preserves a
recorded reading position; sending an explicit null would erase it silently in production)."""

import pytest
from lunaris_api.progress import ProgressStoreUnavailableError, SupabaseProgressStore


class _FakeQuery:
    def __init__(self, sink: list[dict]) -> None:
        self._sink = sink

    def upsert(self, row: dict, *, on_conflict: str) -> "_FakeQuery":
        self._sink.append({"row": row, "on_conflict": on_conflict})
        return self

    def execute(self) -> object:
        return type("Response", (), {"data": []})()


class _FakeClient:
    """Records every upsert the store issues, keyed by table."""

    def __init__(self) -> None:
        self.upserts: list[dict] = []

    def table(self, _name: str) -> _FakeQuery:
        return _FakeQuery(self.upserts)


async def test_positioned_touch_sends_the_lesson_id() -> None:
    # Arrange
    client = _FakeClient()
    store = SupabaseProgressStore(client=client)

    # Act
    await store.touch_course(user_id="user-a", course_id="c-1", last_lesson_id="m-1-l0")

    # Assert
    (upsert,) = client.upserts
    assert upsert["row"]["last_lesson_id"] == "m-1-l0"
    assert upsert["on_conflict"] == "user_id,course_id"


async def test_bare_touch_omits_the_lesson_column_entirely() -> None:
    # Arrange
    client = _FakeClient()
    store = SupabaseProgressStore(client=client)

    # Act
    await store.touch_course(user_id="user-a", course_id="c-1")

    # Assert — the KEY invariant: absent, not null (null would erase the recorded position).
    (upsert,) = client.upserts
    assert "last_lesson_id" not in upsert["row"]
    assert upsert["row"]["last_opened_at"]


async def test_touch_failure_maps_to_the_domain_error() -> None:
    # Arrange — a client whose write blows up (backend outage).
    class _ExplodingClient:
        def table(self, _name: str) -> object:
            raise RuntimeError("connection refused")

    store = SupabaseProgressStore(client=_ExplodingClient())

    # Act / Assert
    with pytest.raises(ProgressStoreUnavailableError):
        await store.touch_course(user_id="user-a", course_id="c-1")
