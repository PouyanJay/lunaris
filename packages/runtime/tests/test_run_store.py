"""Run-store tests: the in-memory fallback's behavior, and the Supabase store's row mapping +
query construction proven against a fake client (no live Postgres in CI)."""

from lunaris_runtime.persistence import InMemoryRunStore, SupabaseRunStore
from lunaris_runtime.schema import RunStatus


async def test_start_then_finish_updates_status_and_counts() -> None:
    # Arrange
    store = InMemoryRunStore()
    await store.start(run_id="r-1", course_id="c-1", topic="binary search")

    # Act
    await store.finish(course_id="c-1", status=RunStatus.COMPLETED, kc_count=5, module_count=3)

    # Assert
    runs = await store.list_recent()
    assert len(runs) == 1
    assert runs[0].id == "c-1"
    assert runs[0].run_id == "r-1"
    assert runs[0].topic == "binary search"
    assert runs[0].status == RunStatus.COMPLETED
    assert runs[0].kc_count == 5
    assert runs[0].module_count == 3


async def test_list_recent_is_newest_first() -> None:
    # Arrange
    store = InMemoryRunStore()
    await store.start(run_id="r-1", course_id="c-1", topic="first")
    await store.start(run_id="r-2", course_id="c-2", topic="second")

    # Act
    runs = await store.list_recent()

    # Assert — most recent insertion leads
    assert [r.id for r in runs] == ["c-2", "c-1"]


async def test_list_recent_honours_the_limit() -> None:
    # Arrange
    store = InMemoryRunStore()
    for index in range(5):
        await store.start(run_id=f"r-{index}", course_id=f"c-{index}", topic="t")

    # Act
    runs = await store.list_recent(limit=2)

    # Assert
    assert [r.id for r in runs] == ["c-4", "c-3"]


async def test_finish_without_start_is_a_noop() -> None:
    # Arrange
    store = InMemoryRunStore()

    # Act — finishing an unrecorded run must not raise or invent a row (best-effort contract)
    await store.finish(course_id="ghost", status=RunStatus.COMPLETED, kc_count=1, module_count=1)

    # Assert
    assert await store.list_recent() == []


# --- SupabaseRunStore: column mapping + query shape, proven without a live DB --------------------


class _FakeResponse:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data


class _FakeQuery:
    """Records the supabase-py builder chain and returns canned rows on execute()."""

    def __init__(self, calls: list[tuple], select_data: list[dict[str, object]]) -> None:
        self._calls = calls
        self._select_data = select_data

    def upsert(self, row: dict[str, object]) -> "_FakeQuery":
        self._calls.append(("upsert", row))
        return self

    def update(self, patch: dict[str, object]) -> "_FakeQuery":
        self._calls.append(("update", patch))
        return self

    def eq(self, column: str, value: object) -> "_FakeQuery":
        self._calls.append(("eq", column, value))
        return self

    def select(self, columns: str) -> "_FakeQuery":
        self._calls.append(("select", columns))
        return self

    def order(self, column: str, desc: bool = False) -> "_FakeQuery":
        self._calls.append(("order", column, desc))
        return self

    def limit(self, count: int) -> "_FakeQuery":
        self._calls.append(("limit", count))
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


def _store_with(client: _FakeClient) -> SupabaseRunStore:
    # Inject the fake via the public constructor seam — no creds, no network, no private reach-in.
    return SupabaseRunStore(client=client)


async def test_supabase_start_upserts_a_running_row() -> None:
    # Arrange
    client = _FakeClient()
    store = _store_with(client)

    # Act
    await store.start(run_id="r-1", course_id="c-1", topic="graphs")

    # Assert — upsert into course_runs with the RUNNING lifecycle status
    assert ("table", "course_runs") in client.calls
    upserts = [call[1] for call in client.calls if call[0] == "upsert"]
    assert upserts == [{"id": "c-1", "run_id": "r-1", "topic": "graphs", "status": "running"}]


async def test_supabase_finish_updates_status_counts_for_the_course() -> None:
    # Arrange
    client = _FakeClient()
    store = _store_with(client)

    # Act
    await store.finish(course_id="c-1", status=RunStatus.COMPLETED, kc_count=7, module_count=4)

    # Assert — an UPDATE on course_runs scoped to the course_id with the terminal status + counts
    assert ("table", "course_runs") in client.calls
    updates = [call[1] for call in client.calls if call[0] == "update"]
    assert len(updates) == 1
    patch = updates[0]
    assert patch["status"] == "completed"
    assert patch["kc_count"] == 7
    assert patch["module_count"] == 4
    assert "updated_at" in patch  # finish stamps the update time
    assert ("eq", "id", "c-1") in client.calls


async def test_supabase_list_recent_maps_rows_newest_first() -> None:
    # Arrange — canned DB rows (snake_case columns, ISO timestamps)
    rows = [
        {
            "id": "c-2",
            "run_id": "r-2",
            "topic": "second",
            "status": "completed",
            "kc_count": 3,
            "module_count": 2,
            "created_at": "2026-05-31T08:00:00+00:00",
            "updated_at": "2026-05-31T08:01:00+00:00",
        },
        {
            "id": "c-1",
            "run_id": "r-1",
            "topic": "first",
            "status": "failed",
            "kc_count": 0,
            "module_count": 0,
            "created_at": "2026-05-31T07:00:00+00:00",
            "updated_at": "2026-05-31T07:00:30+00:00",
        },
    ]
    client = _FakeClient(select_data=rows)
    store = _store_with(client)

    # Act
    runs = await store.list_recent(limit=10)

    # Assert — rows map to CourseRun objects with the right types; query reads course_runs
    # sorted created_at desc, limited.
    assert ("table", "course_runs") in client.calls
    assert [r.id for r in runs] == ["c-2", "c-1"]
    assert runs[0].status == RunStatus.COMPLETED
    assert runs[1].status == RunStatus.FAILED
    assert runs[0].kc_count == 3
    # The ISO timestamptz string is parsed into a tz-aware datetime, not left as a string.
    assert runs[0].created_at.tzinfo is not None
    assert runs[0].created_at.year == 2026
    assert ("order", "created_at", True) in client.calls
    assert ("limit", 10) in client.calls
