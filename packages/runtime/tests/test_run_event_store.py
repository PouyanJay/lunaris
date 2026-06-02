"""Run-event-store tests: the in-memory replay log's append/order/delete contract (the no-key
fallback and test stub), and the Supabase-backed log's row mapping + query shape proven against a
fake client (no live Postgres in CI)."""

from lunaris_runtime.persistence import InMemoryRunEventStore, SupabaseRunEventStore
from lunaris_runtime.schema import RunEvent, RunEventKind


def _event(run_id: str, course_id: str, seq: int, kind: RunEventKind) -> RunEvent:
    return RunEvent(
        run_id=run_id, course_id=course_id, seq=seq, kind=kind, payload={"stage": "graph_built"}
    )


async def test_append_then_list_returns_events_in_seq_order() -> None:
    # Arrange — append out of seq order to prove the read sorts, not the insertion order.
    store = InMemoryRunEventStore()
    await store.append(
        events=[
            _event("r-1", "c-1", 2, RunEventKind.AGENT),
            _event("r-1", "c-1", 0, RunEventKind.PROGRESS),
            _event("r-1", "c-1", 1, RunEventKind.AGENT),
        ]
    )

    # Act
    events = await store.list_for_run(run_id="r-1")

    # Assert — ascending seq, gap-free emission order.
    assert [e.seq for e in events] == [0, 1, 2]
    assert events[0].kind == RunEventKind.PROGRESS


async def test_list_for_unknown_run_is_empty() -> None:
    # Arrange
    store = InMemoryRunEventStore()

    # Act / Assert — no trace → empty (the "no build record" replay state), never an error.
    assert await store.list_for_run(run_id="ghost") == []


async def test_logs_are_isolated_per_run() -> None:
    # Arrange — two runs of two different courses share one store.
    store = InMemoryRunEventStore()
    await store.append(events=[_event("r-1", "c-1", 0, RunEventKind.PROGRESS)])
    await store.append(events=[_event("r-2", "c-2", 0, RunEventKind.PROGRESS)])

    # Act / Assert — a read for one run never bleeds the other's events.
    assert [e.run_id for e in await store.list_for_run(run_id="r-1")] == ["r-1"]
    assert [e.run_id for e in await store.list_for_run(run_id="r-2")] == ["r-2"]


async def test_delete_for_course_purges_all_its_runs() -> None:
    # Arrange — one course, two runs; plus an unrelated course that must survive.
    store = InMemoryRunEventStore()
    await store.append(events=[_event("r-1", "c-1", 0, RunEventKind.PROGRESS)])
    await store.append(events=[_event("r-2", "c-1", 0, RunEventKind.PROGRESS)])
    await store.append(events=[_event("r-3", "c-2", 0, RunEventKind.PROGRESS)])

    # Act
    removed = await store.delete_for_course(course_id="c-1")

    # Assert — both of c-1's runs gone, count reported, c-2 untouched.
    assert removed == 2
    assert await store.list_for_run(run_id="r-1") == []
    assert await store.list_for_run(run_id="r-2") == []
    assert len(await store.list_for_run(run_id="r-3")) == 1


async def test_delete_for_unknown_course_is_a_noop() -> None:
    # Arrange
    store = InMemoryRunEventStore()
    await store.append(events=[_event("r-1", "c-1", 0, RunEventKind.PROGRESS)])

    # Act / Assert — idempotent: nothing matched, nothing removed, existing log intact.
    assert await store.delete_for_course(course_id="absent") == 0
    assert len(await store.list_for_run(run_id="r-1")) == 1


# --- SupabaseRunEventStore: column mapping + query shape, proven without a live DB ---------------


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

    def insert(self, rows: list[dict[str, object]]) -> "_FakeQuery":
        self._calls.append(("insert", rows))
        return self

    def select(self, columns: str) -> "_FakeQuery":
        self._calls.append(("select", columns))
        return self

    def delete(self, count: str | None = None) -> "_FakeQuery":
        self._calls.append(("delete", count))
        self._is_delete = True
        return self

    def eq(self, column: str, value: object) -> "_FakeQuery":
        self._calls.append(("eq", column, value))
        return self

    def order(self, column: str, desc: bool = False) -> "_FakeQuery":
        self._calls.append(("order", column, desc))
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


def _store_with(client: _FakeClient) -> SupabaseRunEventStore:
    # Inject the fake via the public constructor seam — no creds, no network, no private reach-in.
    return SupabaseRunEventStore(client=client)


async def test_supabase_append_inserts_a_batch_of_rows() -> None:
    # Arrange
    client = _FakeClient()
    store = _store_with(client)
    events = [
        RunEvent(
            run_id="r-1", course_id="c-1", seq=0, kind=RunEventKind.PROGRESS, payload={"a": 1}
        ),
        RunEvent(run_id="r-1", course_id="c-1", seq=1, kind=RunEventKind.AGENT, payload={"b": 2}),
    ]

    # Act
    await store.append(events=events)

    # Assert — one batched insert into run_events with the wire columns (kind as its string value).
    assert ("table", "run_events") in client.calls
    inserts = [call[1] for call in client.calls if call[0] == "insert"]
    assert inserts == [
        [
            {
                "run_id": "r-1",
                "course_id": "c-1",
                "seq": 0,
                "kind": "progress",
                "payload": {"a": 1},
            },
            {"run_id": "r-1", "course_id": "c-1", "seq": 1, "kind": "agent", "payload": {"b": 2}},
        ]
    ]


async def test_supabase_append_of_nothing_skips_the_db() -> None:
    # Arrange
    client = _FakeClient()
    store = _store_with(client)

    # Act — an empty flush must not issue a no-op insert.
    await store.append(events=[])

    # Assert
    assert client.calls == []


async def test_supabase_list_for_run_maps_rows_in_seq_order() -> None:
    # Arrange — canned DB rows (snake_case columns; jsonb payload arrives as a dict).
    rows = [
        {
            "run_id": "r-1",
            "course_id": "c-1",
            "seq": 0,
            "kind": "progress",
            "payload": {"stage": "graph_built"},
        },
        {
            "run_id": "r-1",
            "course_id": "c-1",
            "seq": 1,
            "kind": "agent",
            "payload": {"kind": "reasoning"},
        },
    ]
    client = _FakeClient(select_data=rows)
    store = _store_with(client)

    # Act
    events = await store.list_for_run(run_id="r-1")

    # Assert — rows map to RunEvent objects; the query reads run_events scoped to run_id, seq asc.
    assert ("table", "run_events") in client.calls
    assert [e.seq for e in events] == [0, 1]
    assert events[0].kind == RunEventKind.PROGRESS
    assert events[1].payload == {"kind": "reasoning"}
    assert ("eq", "run_id", "r-1") in client.calls
    assert ("order", "seq", False) in client.calls


async def test_supabase_delete_for_course_returns_the_exact_count() -> None:
    # Arrange — the DB reports two rows removed for the course.
    client = _FakeClient(delete_count=2)
    store = _store_with(client)

    # Act
    removed = await store.delete_for_course(course_id="c-1")

    # Assert — a DELETE on run_events scoped to course_id, with an exact count requested.
    assert removed == 2
    assert ("table", "run_events") in client.calls
    assert ("delete", "exact") in client.calls
    assert ("eq", "course_id", "c-1") in client.calls
