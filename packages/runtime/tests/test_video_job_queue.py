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


async def test_update_status_reflects_an_in_flight_stage() -> None:
    # Arrange — a claimed (in-flight) job; the worker reports its render stage.
    queue = InMemoryVideoJobQueue()
    await queue.enqueue(_job())
    await queue.claim(worker_id="worker-a")

    # Act
    await queue.update_status(job_id="job-1", status=VideoJobStatus.RENDERING)

    # Assert — the status poll now reads the real stage (the reader's progress bar).
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.RENDERING


async def test_update_status_never_resurrects_a_settled_job() -> None:
    # Arrange — a job that already settled READY (a late stage write races the settle).
    queue = InMemoryVideoJobQueue()
    await queue.enqueue(_job())
    await queue.claim(worker_id="worker-a")
    await queue.complete(job_id="job-1")

    # Act — a stale stage write must NOT move it back to a working status.
    await queue.update_status(job_id="job-1", status=VideoJobStatus.RENDERING)

    # Assert — still READY (best-effort: a terminal job is never un-settled).
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.READY


async def test_update_status_on_a_vanished_job_is_a_silent_noop() -> None:
    # Arrange — no such job (e.g. reaped). A progress write must never raise (unlike the settles).
    queue = InMemoryVideoJobQueue()

    # Act / Assert — no PersistenceError; just a no-op.
    await queue.update_status(job_id="ghost", status=VideoJobStatus.RENDERING)


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


# ── lease sweep (V7-T4) ───────────────────────────────────────────────────────────


async def test_sweep_requeues_a_stale_in_flight_job() -> None:
    # Arrange — a job claimed at 10:00 by a worker that then "died"; the sweep runs at 10:10.
    now = [datetime(2026, 6, 14, 10, 0, 0, tzinfo=UTC)]
    queue = InMemoryVideoJobQueue(clock=lambda: now[0])
    await queue.enqueue(_job())
    await queue.claim(worker_id="dead-worker")  # status=planning, claimed_at=10:00, attempts=1
    now[0] = datetime(2026, 6, 14, 10, 10, 0, tzinfo=UTC)  # 10 min later → past a 300s lease

    # Act
    result = await queue.sweep_stale_leases(lease_seconds=300, max_attempts=3)

    # Assert — back to queued (attempts left), lease cleared, ready for a fresh claim.
    assert (result.requeued, result.dead_lettered) == (1, 0)
    job = await queue.get(job_id="job-1")
    assert job is not None
    assert job.status == VideoJobStatus.QUEUED
    assert job.claimed_at is None and job.claimed_by is None


async def test_sweep_dead_letters_a_stale_job_past_max_attempts() -> None:
    # Arrange — same stale setup, but the job has already used up its one allowed attempt.
    now = [datetime(2026, 6, 14, 10, 0, 0, tzinfo=UTC)]
    queue = InMemoryVideoJobQueue(clock=lambda: now[0])
    await queue.enqueue(_job())
    await queue.claim(worker_id="dead-worker")  # attempts=1
    now[0] = datetime(2026, 6, 14, 10, 10, 0, tzinfo=UTC)

    # Act
    result = await queue.sweep_stale_leases(lease_seconds=300, max_attempts=1)

    # Assert — dead-lettered, not requeued: a poison job can't loop forever.
    assert (result.requeued, result.dead_lettered) == (0, 1)
    job = await queue.get(job_id="job-1")
    assert job is not None
    assert job.status == VideoJobStatus.FAILED
    assert job.error is not None and "lease expired" in job.error


async def test_sweep_leaves_fresh_queued_and_terminal_jobs_untouched() -> None:
    # Arrange — a fresh in-flight job (just claimed), a queued job, and a completed one.
    now = [datetime(2026, 6, 14, 10, 0, 0, tzinfo=UTC)]
    queue = InMemoryVideoJobQueue(clock=lambda: now[0])
    await queue.enqueue(_job("in-flight"))
    await queue.claim(worker_id="live-worker")  # claimed_at=10:00
    await queue.enqueue(_job("queued"))
    await queue.enqueue(_job("done"))
    await queue.claim(worker_id="live-worker")  # claims the next oldest queued ("queued")
    await queue.complete(job_id="queued")
    now[0] = datetime(2026, 6, 14, 10, 1, 0, tzinfo=UTC)  # only 1 min later → within a 300s lease

    # Act
    result = await queue.sweep_stale_leases(lease_seconds=300, max_attempts=3)

    # Assert — nothing reaped: the live lease is fresh, queued isn't in-flight, done is terminal.
    assert (result.requeued, result.dead_lettered) == (0, 0)
    in_flight = await queue.get(job_id="in-flight")
    assert in_flight is not None and in_flight.status == VideoJobStatus.PLANNING


async def test_list_and_delete_for_course_are_owner_and_course_scoped() -> None:
    # Arrange — two courses for one owner, plus another owner's job that must be untouched.
    owner = "00000000-0000-0000-0000-00000000000a"
    other = "00000000-0000-0000-0000-00000000000b"
    queue = InMemoryVideoJobQueue()
    await queue.enqueue(
        VideoJob(id="a1", user_id=owner, course_id="c1", kind=VideoKind.SUMMARY, input_hash="h")
    )
    await queue.enqueue(
        VideoJob(
            id="a2",
            user_id=owner,
            course_id="c1",
            lesson_id="l1",
            kind=VideoKind.LESSON,
            input_hash="h",
        )
    )
    await queue.enqueue(
        VideoJob(id="a3", user_id=owner, course_id="c2", kind=VideoKind.SUMMARY, input_hash="h")
    )
    await queue.enqueue(
        VideoJob(id="b1", user_id=other, course_id="c1", kind=VideoKind.SUMMARY, input_hash="h")
    )

    # Act / Assert — list returns only this owner's jobs for the course.
    listed = await queue.list_for_course(course_id="c1", owner_id=owner)
    assert sorted(job.id for job in listed) == ["a1", "a2"]

    # Delete removes exactly those rows; the other course + other owner are untouched.
    deleted = await queue.delete_for_course(course_id="c1", owner_id=owner)
    assert deleted == 2
    assert await queue.get(job_id="a1") is None
    assert await queue.get(job_id="a3") is not None  # other course kept
    assert await queue.get(job_id="b1") is not None  # other owner kept


# ── Supabase queue: sweep / list / delete query construction ───────────────────────


async def test_sweep_calls_the_rpc_and_maps_the_counts() -> None:
    # Arrange — the DB function returns the two counts as one row.
    client = _FakeClient(data=[{"requeued": 2, "dead_lettered": 1}])
    queue = SupabaseVideoJobQueue(client=client)

    # Act
    result = await queue.sweep_stale_leases(lease_seconds=300, max_attempts=3)

    # Assert — the atomic requeue/dead-letter is the DB function's job; the client just calls it.
    assert client.calls[0]["table"] == "rpc:requeue_stale_video_jobs"
    assert client.calls[0]["params"] == {"p_lease_seconds": 300, "p_max_attempts": 3}
    assert (result.requeued, result.dead_lettered) == (2, 1)


async def test_delete_for_course_filters_by_owner_and_course_and_counts() -> None:
    # Arrange — the delete matches two rows.
    client = _FakeClient(update_count=2)
    queue = SupabaseVideoJobQueue(client=client)

    # Act
    deleted = await queue.delete_for_course(course_id="c1", owner_id="owner-1")

    # Assert — owner + course filtered, exact count returned (the storage objects go separately).
    call = client.calls[0]
    assert call["op"] == "delete"
    assert call["count_mode"] == "exact"
    assert call["filters"] == {"user_id": "owner-1", "course_id": "c1"}
    assert deleted == 2


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

    def delete(self, count: str | None = None) -> "_FakeQuery":
        self._call["op"] = "delete"
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
        count = (
            self._update_count if self._call.get("op") in ("update", "delete") else len(self._data)
        )
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
