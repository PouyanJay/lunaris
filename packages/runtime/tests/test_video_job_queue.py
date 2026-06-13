"""Video-job queue tests: the in-memory double's claim/lease semantics (including concurrent
claimers), and the Supabase queue's row mapping + query construction against a fake client
(no live Postgres in CI — the SKIP LOCKED atomicity itself is proven live in tests/db)."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from lunaris_runtime.persistence import (
    InMemoryVideoJobQueue,
    PersistenceError,
    SupabaseVideoJobQueue,
)
from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind


def _job(job_id: str = "job-1", owner: str = "00000000-0000-0000-0000-000000000001") -> VideoJob:
    return VideoJob(
        id=job_id,
        user_id=owner,
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="hash-1",
    )


# ── in-memory double ────────────────────────────────────────────────────────────────


async def test_claim_returns_the_job_with_a_lease() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    await queue.enqueue(_job())

    # Act
    claimed = await queue.claim(worker_id="worker-a")

    # Assert — the claim flips the status, stamps the lease, and counts the attempt.
    assert claimed is not None
    assert claimed.id == "job-1"
    assert claimed.status == VideoJobStatus.PLANNING
    assert claimed.claimed_by == "worker-a"
    assert claimed.claimed_at is not None
    assert claimed.attempts == 1


async def test_claim_on_an_empty_queue_returns_none() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()

    # Act / Assert
    assert await queue.claim(worker_id="worker-a") is None


async def test_claims_drain_oldest_first() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    await queue.enqueue(_job("job-1"))
    await queue.enqueue(_job("job-2"))

    # Act
    first = await queue.claim(worker_id="worker-a")
    second = await queue.claim(worker_id="worker-b")

    # Assert — FIFO: the queue is fair to the oldest request.
    assert (first.id, second.id) == ("job-1", "job-2")  # type: ignore[union-attr]


async def test_concurrent_claimers_never_get_the_same_job() -> None:
    # Arrange — more claimers than jobs.
    queue = InMemoryVideoJobQueue()
    for index in range(5):
        await queue.enqueue(_job(f"job-{index}"))

    # Act — ten claimers scheduled concurrently; the Lock serializes them, so the claim
    # invariant must hold under any asyncio interleaving.
    results = await asyncio.gather(
        *(queue.claim(worker_id=f"worker-{index}") for index in range(10))
    )

    # Assert — every job claimed exactly once; the losers got None, never a duplicate.
    claimed_ids = [job.id for job in results if job is not None]
    assert sorted(claimed_ids) == [f"job-{index}" for index in range(5)]
    assert results.count(None) == 5


async def test_complete_marks_the_job_ready() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    await queue.enqueue(_job())
    await queue.claim(worker_id="worker-a")

    # Act
    await queue.complete(job_id="job-1")

    # Assert
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.READY


async def test_fail_records_the_error() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    await queue.enqueue(_job())
    await queue.claim(worker_id="worker-a")

    # Act
    await queue.fail(job_id="job-1", error="render exploded")

    # Assert
    job = await queue.get(job_id="job-1")
    assert job is not None
    assert job.status == VideoJobStatus.FAILED
    assert job.error == "render exploded"


async def test_heartbeat_refreshes_the_lease() -> None:
    # Arrange — an injected clock makes lease timing deterministic (no sleeps).
    ticks = iter(
        [
            datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC),  # enqueue
            datetime(2026, 6, 12, 10, 0, 1, tzinfo=UTC),  # claim
            datetime(2026, 6, 12, 10, 5, 0, tzinfo=UTC),  # heartbeat
        ]
    )
    queue = InMemoryVideoJobQueue(clock=lambda: next(ticks))
    await queue.enqueue(_job())
    claimed = await queue.claim(worker_id="worker-a")
    assert claimed is not None and claimed.claimed_at is not None

    # Act
    await queue.heartbeat(job_id="job-1")

    # Assert — the lease moved forward; a requeue sweep would not reap this worker.
    job = await queue.get(job_id="job-1")
    assert job is not None
    assert job.claimed_at == datetime(2026, 6, 12, 10, 5, 0, tzinfo=UTC)
    assert job.claimed_at > claimed.claimed_at


async def test_writes_against_an_unknown_job_raise() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()

    # Act / Assert — settling or heart-beating a job the queue never saw is a bug surfacing,
    # not a no-op (protocol contract: job state is never silently wrong).
    with pytest.raises(PersistenceError):
        await queue.heartbeat(job_id="ghost")
    with pytest.raises(PersistenceError):
        await queue.complete(job_id="ghost")
    with pytest.raises(PersistenceError):
        await queue.fail(job_id="ghost", error="boom")


async def test_get_scopes_to_the_owner() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    await queue.enqueue(_job(owner="00000000-0000-0000-0000-00000000000a"))

    # Act / Assert — the owner sees the job; anyone else gets nothing.
    assert await queue.get(job_id="job-1", owner_id="00000000-0000-0000-0000-00000000000a")
    assert await queue.get(job_id="job-1", owner_id="someone-else") is None
    assert await queue.get(job_id="ghost") is None


# ── Supabase queue: query construction + row mapping against a fake client ─────────


class _FakeQuery:
    """Records the PostgREST call chain and returns a canned response (data + count)."""

    def __init__(
        self,
        sink: list[dict[str, Any]],
        table: str,
        data: list[dict[str, Any]],
        update_count: int,
    ) -> None:
        self._sink = sink
        self._call: dict[str, Any] = {"table": table, "filters": {}}
        self._data = data
        self._update_count = update_count

    def insert(self, row: dict[str, Any]) -> "_FakeQuery":
        self._call["op"] = "insert"
        self._call["row"] = row
        return self

    def update(self, patch: dict[str, Any], count: str | None = None) -> "_FakeQuery":
        self._call["op"] = "update"
        self._call["patch"] = patch
        self._call["count_mode"] = count
        return self

    def select(self, columns: str) -> "_FakeQuery":
        self._call["op"] = "select"
        self._call["columns"] = columns
        return self

    def eq(self, column: str, value: Any) -> "_FakeQuery":
        self._call["filters"][column] = value
        return self

    def limit(self, n: int) -> "_FakeQuery":
        return self

    def execute(self) -> Any:
        self._sink.append(self._call)
        count = self._update_count if self._call.get("op") == "update" else len(self._data)
        return type("Response", (), {"data": self._data, "count": count})()


class _FakeClient:
    def __init__(self, data: list[dict[str, Any]] | None = None, *, update_count: int = 1) -> None:
        self.calls: list[dict[str, Any]] = []
        self._data = data or []
        self._update_count = update_count

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self.calls, name, self._data, self._update_count)

    def rpc(self, name: str, params: dict[str, Any]) -> _FakeQuery:
        query = _FakeQuery(self.calls, f"rpc:{name}", self._data, self._update_count)
        query._call["op"] = "rpc"
        query._call["params"] = params
        return query


_ROW = {
    "id": "job-1",
    "user_id": "00000000-0000-0000-0000-000000000001",
    "course_id": "course-1",
    "lesson_id": "lesson-1",
    "kind": "lesson",
    "status": "planning",
    "input_hash": "hash-1",
    "contract_hash": None,
    "config": {},
    "attempts": 1,
    "claimed_at": "2026-06-12T10:00:00+00:00",
    "claimed_by": "worker-a",
    "error": None,
    "created_at": "2026-06-12T09:59:00+00:00",
    "updated_at": "2026-06-12T10:00:00+00:00",
}


async def test_enqueue_inserts_the_queued_row() -> None:
    # Arrange
    client = _FakeClient()
    queue = SupabaseVideoJobQueue(client=client)

    # Act
    await queue.enqueue(_job())

    # Assert — the row carries the queue contract; timestamps stay DB-owned.
    call = client.calls[0]
    assert call["table"] == "video_jobs"
    assert call["op"] == "insert"
    assert call["row"] == {
        "id": "job-1",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "course_id": "course-1",
        "lesson_id": "lesson-1",
        "kind": "lesson",
        "status": "queued",
        "input_hash": "hash-1",
        "config": {},
    }


async def test_claim_calls_the_rpc_and_maps_the_row() -> None:
    # Arrange
    client = _FakeClient(data=[_ROW])
    queue = SupabaseVideoJobQueue(client=client)

    # Act
    job = await queue.claim(worker_id="worker-a")

    # Assert — the atomic claim is the DB function's job; the client just calls it.
    assert client.calls[0]["table"] == "rpc:claim_video_job"
    assert client.calls[0]["params"] == {"p_worker": "worker-a"}
    assert job is not None
    assert job.status == VideoJobStatus.PLANNING
    assert job.claimed_by == "worker-a"
    assert job.kind == VideoKind.LESSON


async def test_claim_maps_an_empty_queue_to_none() -> None:
    # Arrange
    client = _FakeClient(data=[])
    queue = SupabaseVideoJobQueue(client=client)

    # Act / Assert
    assert await queue.claim(worker_id="worker-a") is None


async def test_complete_patches_status_by_id() -> None:
    # Arrange
    client = _FakeClient()
    queue = SupabaseVideoJobQueue(client=client)

    # Act
    await queue.complete(job_id="job-1")

    # Assert — ready clears any stale error and stamps updated_at (app-maintained, no trigger).
    call = client.calls[0]
    assert call["op"] == "update"
    assert call["patch"]["status"] == "ready"
    assert call["patch"]["error"] is None
    assert "updated_at" in call["patch"]
    assert call["filters"] == {"id": "job-1"}


async def test_heartbeat_patches_the_lease_timestamps() -> None:
    # Arrange
    client = _FakeClient()
    queue = SupabaseVideoJobQueue(client=client)

    # Act
    await queue.heartbeat(job_id="job-1")

    # Assert
    call = client.calls[0]
    assert call["op"] == "update"
    assert "claimed_at" in call["patch"]
    assert "updated_at" in call["patch"]
    assert call["filters"] == {"id": "job-1"}


async def test_patching_a_vanished_job_raises() -> None:
    # Arrange — the update matches zero rows (the job was reaped or never existed).
    client = _FakeClient(update_count=0)
    queue = SupabaseVideoJobQueue(client=client)

    # Act / Assert — mirrors the in-memory double: never a silent no-op.
    with pytest.raises(PersistenceError):
        await queue.complete(job_id="ghost")


async def test_fail_patches_status_and_error_by_id() -> None:
    # Arrange
    client = _FakeClient()
    queue = SupabaseVideoJobQueue(client=client)

    # Act
    await queue.fail(job_id="job-1", error="render exploded")

    # Assert
    call = client.calls[0]
    assert call["patch"]["status"] == "failed"
    assert call["patch"]["error"] == "render exploded"
    assert call["filters"] == {"id": "job-1"}


async def test_get_scopes_to_the_owner_filter() -> None:
    # Arrange
    client = _FakeClient(data=[_ROW])
    queue = SupabaseVideoJobQueue(client=client)

    # Act
    job = await queue.get(job_id="job-1", owner_id="00000000-0000-0000-0000-000000000001")

    # Assert — owner_id becomes an explicit user_id filter (app belt over the DB belt).
    assert client.calls[0]["columns"] == "*"
    assert client.calls[0]["filters"] == {
        "id": "job-1",
        "user_id": "00000000-0000-0000-0000-000000000001",
    }
    assert job is not None and job.id == "job-1"
