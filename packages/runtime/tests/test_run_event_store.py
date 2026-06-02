"""Run-event-store tests: the in-memory replay log's append/order/delete contract (the no-key
fallback and test stub). The Supabase-backed log's row mapping is proven in T1."""

from lunaris_runtime.persistence import InMemoryRunEventStore
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
