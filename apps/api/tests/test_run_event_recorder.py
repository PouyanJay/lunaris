"""Unit tests for RunEventRecorder — the per-run buffer that flushes the streamed build log to the
event store in best-effort batches, with a volume cap. Drives the batching/cap behavior in isolation
(the end-to-end persistence is covered by test_run_events_api)."""

from collections.abc import Sequence

from lunaris_api.run_event_recorder import RunEventRecorder
from lunaris_runtime.schema import (
    AgentEvent,
    AgentEventKind,
    ProgressEvent,
    ProgressStage,
    RunEvent,
)
from structlog.testing import capture_logs


class _RecordingStore:
    """Captures every flushed batch so the test can assert batch boundaries + ordering."""

    def __init__(self) -> None:
        self.batches: list[list[RunEvent]] = []
        self.owner_ids: list[str | None] = []

    async def append(self, *, events: Sequence[RunEvent], owner_id: str | None = None) -> None:
        self.batches.append(list(events))
        self.owner_ids.append(owner_id)

    async def list_for_run(self, *, run_id: str, owner_id: str | None = None) -> list[RunEvent]:
        return [event for batch in self.batches for event in batch]

    async def delete_for_course(self, *, course_id: str, owner_id: str | None = None) -> int:
        return 0


def _progress(stage: ProgressStage) -> tuple[str, ProgressEvent]:
    return ("progress", ProgressEvent(stage=stage, label="x", run_id="r1"))


def _agent() -> tuple[str, AgentEvent]:
    return ("agent", AgentEvent(kind=AgentEventKind.REASONING, run_id="r1", text="thinking"))


def _recorder(store: object, *, cap: int = 5000, batch_size: int = 50) -> RunEventRecorder:
    return RunEventRecorder(store, run_id="r1", course_id="c1", cap=cap, batch_size=batch_size)


async def test_flushes_at_a_phase_boundary() -> None:
    # Arrange — a recorder with a large batch size so only the phase boundary can trigger a flush.
    store = _RecordingStore()
    recorder = _recorder(store, batch_size=1000)

    # Act — two agent beats then a progress (phase) beat.
    await recorder.record(_agent())
    await recorder.record(_agent())
    assert store.batches == []  # buffered, not yet flushed
    await recorder.record(_progress(ProgressStage.GRAPH_BUILT))

    # Assert — the phase beat flushes itself plus the two buffered agent beats, in seq order.
    assert len(store.batches) == 1
    assert [e.seq for e in store.batches[0]] == [0, 1, 2]
    assert [e.kind.value for e in store.batches[0]] == ["agent", "agent", "progress"]


async def test_flushes_when_the_batch_fills() -> None:
    # Arrange — batch size 3, no phase beats, so only a full buffer can flush.
    store = _RecordingStore()
    recorder = _recorder(store, batch_size=3)

    # Act
    for _ in range(7):
        await recorder.record(_agent())

    # Assert — two full batches of 3 flushed; the 7th sits buffered until an explicit flush.
    assert [len(b) for b in store.batches] == [3, 3]
    await recorder.flush()
    assert [len(b) for b in store.batches] == [3, 3, 1]
    assert [e.seq for e in store.batches[2]] == [6]


async def test_flush_of_an_empty_buffer_is_a_noop() -> None:
    # Arrange
    store = _RecordingStore()
    recorder = _recorder(store)

    # Act / Assert — nothing buffered → no batch issued.
    await recorder.flush()
    assert store.batches == []


async def test_cap_drops_excess_and_logs_once() -> None:
    # Arrange — cap 2; the 3rd and 4th events must be dropped, the note logged exactly once.
    store = _RecordingStore()
    recorder = _recorder(store, cap=2, batch_size=1000)

    # Act
    with capture_logs() as logs:
        for _ in range(4):
            await recorder.record(_agent())
        await recorder.flush()

    # Assert — only the first two events persisted; seq never exceeds the cap.
    persisted = [e for batch in store.batches for e in batch]
    assert [e.seq for e in persisted] == [0, 1]
    truncations = [e for e in logs if e["event"] == "run_events_truncated"]
    assert len(truncations) == 1
    assert truncations[0]["run_id"] == "r1" and truncations[0]["cap"] == 2


async def test_course_frame_is_never_recorded() -> None:
    # Arrange
    store = _RecordingStore()
    recorder = _recorder(store, batch_size=1)

    # Act — the terminal ("course", ...) frame is the build's result, not a transcript beat.
    await recorder.record(("course", object()))

    # Assert
    assert store.batches == []


async def test_owner_id_is_stamped_on_every_flush() -> None:
    # Arrange — a recorder bound to an owner (Phase 2 per-user scoping).
    store = _RecordingStore()
    recorder = RunEventRecorder(store, run_id="r1", course_id="c1", owner_id="user-7", batch_size=1)

    # Act — a phase beat flushes immediately at batch_size=1.
    await recorder.record(_progress(ProgressStage.RUN_STARTED))

    # Assert — the append carried the owner, so the persisted events are scoped to that user.
    assert store.owner_ids == ["user-7"]


class _FailingStore:
    async def append(self, *, events: Sequence[RunEvent], owner_id: str | None = None) -> None:
        raise RuntimeError("event log is down")

    async def list_for_run(self, *, run_id: str, owner_id: str | None = None) -> list[RunEvent]:
        return []

    async def delete_for_course(self, *, course_id: str, owner_id: str | None = None) -> int:
        return 0


async def test_a_failing_flush_never_raises() -> None:
    # Arrange
    recorder = _recorder(_FailingStore(), batch_size=1)

    # Act — a flush whose store raises must be swallowed (best-effort). Reaching the assert below
    # without the RuntimeError propagating out of record() IS the primary no-raise contract.
    with capture_logs() as logs:
        await recorder.record(_agent())

    # Assert — the swallowed failure is logged run_id-correlated (so it was attempted, not skipped).
    failures = [e for e in logs if e["event"] == "run_events_append_failed"]
    assert failures and failures[0]["run_id"] == "r1"


async def test_no_store_is_a_noop() -> None:
    # Arrange / Act — a recorder with no store wired must not raise on record or flush.
    recorder = _recorder(None, batch_size=1)
    await recorder.record(_agent())
    await recorder.flush()
    # Assert — reaching here without error is the contract (the batch/no-key path).
