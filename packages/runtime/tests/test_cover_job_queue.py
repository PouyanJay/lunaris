"""Cover-job queue tests: the in-memory double's claim/lease semantics (including concurrent
claimers), the lease sweep, and the sticky-terminal cancel — mirroring the video-job queue. The
Supabase queue's row mapping is exercised via the API integration tests; these lock the claim/lease
contract the worker relies on."""

import asyncio
from datetime import UTC, datetime

from lunaris_runtime.persistence import InMemoryCoverJobQueue
from lunaris_runtime.schema import CoverJob, CoverJobStatus


def _job(job_id: str = "job-1") -> CoverJob:
    return CoverJob(id=job_id, user_id="u1", course_id="c1", input_hash="h")


async def test_claim_flips_to_art_directing_and_stamps_the_lease() -> None:
    queue = InMemoryCoverJobQueue()
    await queue.enqueue(_job())

    claimed = await queue.claim(worker_id="worker-a")

    assert claimed is not None
    assert claimed.status == CoverJobStatus.ART_DIRECTING  # the first in-flight stage
    assert claimed.claimed_by == "worker-a"
    assert claimed.claimed_at is not None
    assert claimed.attempts == 1


async def test_concurrent_claimers_never_get_the_same_job() -> None:
    queue = InMemoryCoverJobQueue()
    for index in range(5):
        await queue.enqueue(_job(f"job-{index}"))

    results = await asyncio.gather(
        *(queue.claim(worker_id=f"worker-{index}") for index in range(10))
    )

    claimed_ids = sorted(job.id for job in results if job is not None)
    assert claimed_ids == [f"job-{index}" for index in range(5)]


async def test_find_active_dedups_by_course_and_owner() -> None:
    queue = InMemoryCoverJobQueue()
    await queue.enqueue(_job("job-1"))

    active = await queue.find_active(course_id="c1", owner_id="u1")
    assert active is not None and active.id == "job-1"
    # Another owner sees nothing for the same course id.
    assert await queue.find_active(course_id="c1", owner_id="u2") is None


async def test_sweep_requeues_a_stale_in_flight_job() -> None:
    now = [datetime(2026, 7, 10, 10, 0, 0, tzinfo=UTC)]
    queue = InMemoryCoverJobQueue(clock=lambda: now[0])
    await queue.enqueue(_job())
    await queue.claim(worker_id="dead-worker")  # art_directing, claimed_at=10:00, attempts=1
    now[0] = datetime(2026, 7, 10, 10, 10, 0, tzinfo=UTC)  # past a 300s lease

    result = await queue.sweep_stale_leases(lease_seconds=300, max_attempts=3)

    assert (result.requeued, result.dead_lettered) == (1, 0)
    job = await queue.get(job_id="job-1")
    assert job is not None
    assert job.status == CoverJobStatus.QUEUED
    assert job.claimed_at is None and job.claimed_by is None


async def test_sweep_dead_letters_past_max_attempts() -> None:
    now = [datetime(2026, 7, 10, 10, 0, 0, tzinfo=UTC)]
    queue = InMemoryCoverJobQueue(clock=lambda: now[0])
    await queue.enqueue(_job())
    await queue.claim(worker_id="dead-worker")  # attempts=1
    now[0] = datetime(2026, 7, 10, 10, 10, 0, tzinfo=UTC)

    result = await queue.sweep_stale_leases(lease_seconds=300, max_attempts=1)

    assert (result.requeued, result.dead_lettered) == (0, 1)
    job = await queue.get(job_id="job-1")
    assert job is not None
    assert job.status == CoverJobStatus.FAILED
    assert job.error is not None and "lease expired" in job.error


async def test_cancel_is_sticky_terminal_against_a_racing_complete() -> None:
    queue = InMemoryCoverJobQueue()
    await queue.enqueue(_job())
    await queue.claim(worker_id="worker-a")

    assert await queue.cancel(job_id="job-1", owner_id="u1") is True
    # A worker finishing the render a beat later must not revive a cancelled job.
    await queue.complete(job_id="job-1")

    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == CoverJobStatus.CANCELLED


async def test_cancel_is_owner_scoped() -> None:
    queue = InMemoryCoverJobQueue()
    await queue.enqueue(_job())
    # Another user cannot cancel someone else's job.
    assert await queue.cancel(job_id="job-1", owner_id="intruder") is False
