"""Run-event-store tests: the in-memory replay log's append/order/delete contract (the no-key
fallback and test stub), and the Supabase-backed log's row mapping + query shape proven against a
fake client (no live Postgres in CI)."""

import pytest
from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    PersistenceError,
    SupabaseRunEventStore,
)
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


async def test_append_rejects_a_duplicate_seq_for_a_run() -> None:
    # Arrange — the in-memory store mirrors the DB's UNIQUE (run_id, seq) index, so a re-used seq is
    # a failed insert (the constraint a re-claimed video job's seq-0 restart trips), not a silent
    # duplicate.
    store = InMemoryRunEventStore()
    await store.append(events=[_event("r-1", "c-1", 0, RunEventKind.PROGRESS)])

    # Act / Assert
    with pytest.raises(PersistenceError):
        await store.append(events=[_event("r-1", "c-1", 0, RunEventKind.AGENT)])
    # The rejected append is atomic — r-1 still holds only its one original event.
    assert [e.seq for e in await store.list_for_run(run_id="r-1")] == [0]


async def test_latest_seq_is_none_for_a_run_with_no_events() -> None:
    # Arrange / Act / Assert — no events → no seed → a fresh worker starts at 0.
    store = InMemoryRunEventStore()
    assert await store.latest_seq(run_id="ghost") is None


async def test_latest_seq_returns_the_highest_seq() -> None:
    # Arrange
    store = InMemoryRunEventStore()
    await store.append(
        events=[
            _event("r-1", "c-1", 0, RunEventKind.PROGRESS),
            _event("r-1", "c-1", 1, RunEventKind.AGENT),
        ]
    )

    # Act / Assert — the seed a re-claimed worker continues PAST.
    assert await store.latest_seq(run_id="r-1") == 1


async def test_latest_seq_is_none_for_a_non_owner() -> None:
    # Arrange — A's run; B must not learn its seq (mirrors list_for_run's owner scoping).
    store = InMemoryRunEventStore()
    await store.append(events=[_event("r-1", "c-1", 0, RunEventKind.PROGRESS)], owner_id="user-a")

    # Act / Assert
    assert await store.latest_seq(run_id="r-1", owner_id="user-b") is None
    assert await store.latest_seq(run_id="r-1", owner_id="user-a") == 0


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


# --- per-user scoping (Phase 2): another user's transcript reads as empty -----------------------


async def test_list_for_run_is_empty_for_a_non_owner() -> None:
    # Arrange — A's run leaves a transcript.
    store = InMemoryRunEventStore()
    await store.append(events=[_event("r-1", "c-1", 0, RunEventKind.PROGRESS)], owner_id="user-a")

    # Act / Assert — B (a guessed run_id) sees nothing; A sees their own; unscoped sees it too.
    assert await store.list_for_run(run_id="r-1", owner_id="user-b") == []
    assert len(await store.list_for_run(run_id="r-1", owner_id="user-a")) == 1
    assert len(await store.list_for_run(run_id="r-1")) == 1


async def test_delete_for_course_only_purges_the_owners_runs() -> None:
    # Arrange — two users built courses that (pathologically) share a course_id.
    store = InMemoryRunEventStore()
    await store.append(
        events=[_event("r-a", "shared", 0, RunEventKind.PROGRESS)], owner_id="user-a"
    )
    await store.append(
        events=[_event("r-b", "shared", 0, RunEventKind.PROGRESS)], owner_id="user-b"
    )

    # Act — A purges their course; B's identically-keyed log must survive.
    removed = await store.delete_for_course(course_id="shared", owner_id="user-a")

    # Assert
    assert removed == 1
    assert await store.list_for_run(run_id="r-a", owner_id="user-a") == []
    assert len(await store.list_for_run(run_id="r-b", owner_id="user-b")) == 1


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
        self._range: tuple[int, int] | None = None

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

    def range(self, start: int, end: int) -> "_FakeQuery":
        self._calls.append(("range", start, end))
        self._range = (start, end)
        return self

    def limit(self, count: int) -> "_FakeQuery":
        self._calls.append(("limit", count))
        return self

    def execute(self) -> _FakeResponse:
        if self._is_delete:
            return _FakeResponse([], count=self._delete_count)
        if self._range is not None:
            # Mimic Supabase/PostgREST: a request returns at most 1000 rows, even if a wider
            # range is asked for — the cap that forces list_for_run to paginate.
            start, end = self._range
            width = min(end - start + 1, 1000)
            return _FakeResponse(self._select_data[start : start + width])
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


async def test_supabase_list_for_run_paginates_past_the_1000_row_cap() -> None:
    # Arrange — a long (or loopy) build exceeds Supabase's 1000-row-per-request cap. The store must
    # page through every row, or the replay shows a truncated, stuck-mid-build timeline.
    rows = [
        {"run_id": "r-1", "course_id": "c-1", "seq": i, "kind": "agent", "payload": {"i": i}}
        for i in range(2500)
    ]
    client = _FakeClient(select_data=rows)
    store = _store_with(client)

    # Act
    events = await store.list_for_run(run_id="r-1")

    # Assert — all 2500 events returned in seq order (not just the first 1000-row page).
    assert len(events) == 2500
    assert [e.seq for e in events] == list(range(2500))
    # Three pages were requested: 0-999, 1000-1999, 2000-2999 (the last short, ending the loop).
    range_calls = [c for c in client.calls if c[0] == "range"]
    assert range_calls == [("range", 0, 999), ("range", 1000, 1999), ("range", 2000, 2999)]


async def test_supabase_list_for_run_terminates_on_an_exactly_divisible_count() -> None:
    # Arrange — a row count that is an exact multiple of the page size: the last full page must be
    # followed by one empty page that ends the loop (not an infinite loop on the boundary).
    rows = [
        {"run_id": "r-1", "course_id": "c-1", "seq": i, "kind": "agent", "payload": {}}
        for i in range(2000)
    ]
    client = _FakeClient(select_data=rows)
    store = _store_with(client)

    # Act
    events = await store.list_for_run(run_id="r-1")

    # Assert — all 2000 returned; a third (empty) page request terminates the loop.
    assert len(events) == 2000
    range_calls = [c for c in client.calls if c[0] == "range"]
    assert range_calls == [("range", 0, 999), ("range", 1000, 1999), ("range", 2000, 2999)]


async def test_supabase_latest_seq_reads_one_row_seq_desc() -> None:
    # Arrange — the highest-seq row the DB would return for order(seq).desc().limit(1).
    client = _FakeClient(select_data=[{"seq": 7}])
    store = _store_with(client)

    # Act
    latest = await store.latest_seq(run_id="r-1")

    # Assert — a single-row read scoped to the run, ordered seq desc, limited to 1; the seq mapped.
    assert latest == 7
    assert ("table", "run_events") in client.calls
    assert ("eq", "run_id", "r-1") in client.calls
    assert ("order", "seq", True) in client.calls
    assert ("limit", 1) in client.calls


async def test_supabase_latest_seq_is_none_for_a_run_with_no_events() -> None:
    # Arrange — an empty result (a run that never logged, or another owner's).
    client = _FakeClient(select_data=[])
    store = _store_with(client)

    # Act / Assert — no rows → None (the worker then seeds at 0).
    assert await store.latest_seq(run_id="r-1", owner_id="user-7") is None
    assert ("eq", "user_id", "user-7") in client.calls


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


async def test_supabase_append_stamps_the_owner_on_every_row_when_scoped() -> None:
    # Arrange
    client = _FakeClient()
    store = _store_with(client)
    events = [
        RunEvent(run_id="r-1", course_id="c-1", seq=0, kind=RunEventKind.PROGRESS, payload={}),
        RunEvent(run_id="r-1", course_id="c-1", seq=1, kind=RunEventKind.AGENT, payload={}),
    ]

    # Act
    await store.append(events=events, owner_id="user-7")

    # Assert — every inserted row carries user_id (so RLS enforces for any later user-JWT client).
    inserted = next(call[1] for call in client.calls if call[0] == "insert")
    assert all(row["user_id"] == "user-7" for row in inserted)


async def test_supabase_list_for_run_filters_by_owner() -> None:
    # Arrange
    client = _FakeClient(select_data=[])
    store = _store_with(client)

    # Act
    await store.list_for_run(run_id="r-1", owner_id="user-7")

    # Assert — the read only returns the caller's own events.
    assert ("eq", "user_id", "user-7") in client.calls


async def test_supabase_delete_for_course_filters_by_owner() -> None:
    # Arrange
    client = _FakeClient(delete_count=1)
    store = _store_with(client)

    # Act
    await store.delete_for_course(course_id="c-1", owner_id="user-7")

    # Assert — the purge only removes the caller's own events.
    assert ("eq", "user_id", "user-7") in client.calls
