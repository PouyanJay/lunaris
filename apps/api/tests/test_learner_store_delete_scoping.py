"""course-delete T6 — fake-client coverage of the Supabase query the four store cascades ACTUALLY
run in production (the one shape the in-memory cascade tests can't see). Asserts each owner-scoped
`delete_for_course` issues a DELETE scoped by BOTH user_id and course_id with an exact count — the
security-relevant invariant for an irreversible cross-table purge. The grounding corpus (course-only
scoped, no owner column) is covered in packages/grounding/tests/test_supabase_corpus_store.py."""

from lunaris_api.activity import SupabaseActivityStore
from lunaris_api.bookmarks import SupabaseBookmarkStore
from lunaris_api.progress import SupabaseProgressStore


class _FakeQuery:
    """Records the supabase-py builder chain, returning a canned exact-delete count on execute()."""

    def __init__(self, calls: list[tuple], *, delete_count: int) -> None:
        self._calls = calls
        self._delete_count = delete_count

    def delete(self, count: str | None = None) -> "_FakeQuery":
        self._calls.append(("delete", count))
        return self

    def eq(self, column: str, value: object) -> "_FakeQuery":
        self._calls.append(("eq", column, value))
        return self

    def execute(self) -> object:
        return type("Response", (), {"count": self._delete_count, "data": []})()


class _FakeClient:
    def __init__(self, *, delete_count: int = 0) -> None:
        self.calls: list[tuple] = []
        self._delete_count = delete_count

    def table(self, name: str) -> _FakeQuery:
        self.calls.append(("table", name))
        return _FakeQuery(self.calls, delete_count=self._delete_count)


def _scoped_delete(calls: list[tuple], *, table: str, owner: str, course_id: str) -> bool:
    """A DELETE on ``table`` scoped by BOTH user_id and course_id, exact count requested."""
    return (
        ("table", table) in calls
        and ("delete", "exact") in calls
        and ("eq", "user_id", owner) in calls
        and ("eq", "course_id", course_id) in calls
    )


async def test_progress_delete_for_course_scopes_all_three_tables_by_owner_and_course() -> None:
    # Arrange — each of the three progress tables reports one row removed.
    client = _FakeClient(delete_count=1)
    store = SupabaseProgressStore(client=client)

    # Act
    removed = await store.delete_for_course(user_id="user-7", course_id="c-1")

    # Assert — every progress table is DELETEd, owner+course scoped, and the counts sum.
    assert removed == 3
    for table in ("objective_progress", "lesson_progress", "learner_course_state"):
        assert _scoped_delete(client.calls, table=table, owner="user-7", course_id="c-1")


async def test_bookmarks_delete_for_course_scopes_by_owner_and_course() -> None:
    # Arrange
    client = _FakeClient(delete_count=2)
    store = SupabaseBookmarkStore(client=client)

    # Act
    removed = await store.delete_for_course(user_id="user-7", course_id="c-1")

    # Assert
    assert removed == 2
    assert _scoped_delete(client.calls, table="bookmarks", owner="user-7", course_id="c-1")


async def test_activity_delete_for_course_scopes_learning_events_and_leaves_minutes() -> None:
    # Arrange
    client = _FakeClient(delete_count=4)
    store = SupabaseActivityStore(client=client)

    # Act
    removed = await store.delete_for_course(user_id="user-7", course_id="c-1")

    # Assert — only learning_events is purged (owner+course scoped); study_minutes is never touched
    # (it has no course dimension — AD2).
    assert removed == 4
    assert _scoped_delete(client.calls, table="learning_events", owner="user-7", course_id="c-1")
    assert not any(call == ("table", "study_minutes") for call in client.calls)
