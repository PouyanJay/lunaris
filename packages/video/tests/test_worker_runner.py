"""Video V7-T0: the shared worker supervisor — one ``run_video_workers`` both deployments use.

The same ``VideoWorker`` loop runs everywhere (plan §1.1); only the supervision differs:

- the API lifespan starts the supervisor as a background task and **cancels** it on shutdown;
- the standalone worker container (``lunaris_api.worker_entrypoint``) runs it under ``asyncio.run``
  with a **stop event** wired to SIGTERM/SIGINT.

This proves the one supervisor spawns N workers that drain a shared queue, settles a clean shutdown
on either signal, and never orphans a worker task (a job mid-render stays PLANNING for the V7 lease
sweep — no work is lost silently). Synchronisation is event-based (no sleeps): a queue subclass
signals when a worker first polls and when each job settles.
"""

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

import pytest
from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
)
from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind
from lunaris_video import StubVideoPipeline, run_video_workers

_OWNER = "00000000-0000-0000-0000-000000000001"


def _job(index: int) -> VideoJob:
    return VideoJob(
        id=f"job-{index}",
        user_id=_OWNER,
        course_id="c1",
        lesson_id=f"l{index}",
        kind=VideoKind.LESSON,
        input_hash="h",
    )


class _SignallingQueue(InMemoryVideoJobQueue):
    """An in-memory queue that fires events on the first poll and once ``expected`` jobs settle —
    so tests synchronise on real progress, never on a sleep."""

    def __init__(self, *, expected: int = 0) -> None:
        super().__init__()
        self.first_poll = asyncio.Event()
        self.all_settled = asyncio.Event()
        self._remaining = expected

    async def claim(self, *, worker_id: str) -> VideoJob | None:
        self.first_poll.set()  # a worker is alive and polling
        return await super().claim(worker_id=worker_id)

    async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None:
        await super().complete(job_id=job_id, contract_hash=contract_hash)
        self._remaining -= 1
        if self._remaining <= 0:
            self.all_settled.set()


def _supervisor(
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    *,
    count: int,
    stop: asyncio.Event | None,
) -> Coroutine[Any, Any, None]:
    return run_video_workers(
        queue=queue,
        pipeline=StubVideoPipeline(),
        storage=storage,
        events=events,
        count=count,
        poll_interval_seconds=0.001,
        worker_id_prefix="test",
        stop=stop,
    )


async def test_supervisor_drains_queued_jobs_then_stops_on_event() -> None:
    # Arrange — two queued jobs; the queue signals once both settle, two workers over one queue.
    queue = _SignallingQueue(expected=2)
    storage, events = InMemoryVideoStorage(), InMemoryRunEventStore()
    for index in range(2):
        await queue.enqueue(_job(index))
    stop = asyncio.Event()

    async def _stop_when_drained() -> None:
        await queue.all_settled.wait()
        stop.set()  # both rendered → ask the supervisor to return

    # Act — run the supervisor alongside the watcher; setting `stop` must make it return.
    async with asyncio.timeout(10):
        await asyncio.gather(
            _supervisor(queue, storage, events, count=2, stop=stop), _stop_when_drained()
        )

    # Assert — both jobs rendered AND their artifacts landed under the owner/course/job prefix.
    for index in range(2):
        job = await queue.get(job_id=f"job-{index}")
        assert job is not None and job.status == VideoJobStatus.READY
    assert f"{_OWNER}/c1/job-0/final.mp4" in storage.paths()
    assert f"{_OWNER}/c1/job-1/final.mp4" in storage.paths()


async def test_supervisor_returns_promptly_when_stopped_with_empty_queue() -> None:
    # Arrange — nothing to do; once a worker has polled (it is alive and idle), fire the stop. The
    # supervisor must exit cleanly (cancel + drain its idle workers), not hang on the idle poll.
    queue = _SignallingQueue()
    storage, events = InMemoryVideoStorage(), InMemoryRunEventStore()
    stop = asyncio.Event()

    async def _stop_once_polling() -> None:
        await queue.first_poll.wait()
        stop.set()

    async with asyncio.timeout(5):
        await asyncio.gather(
            _supervisor(queue, storage, events, count=2, stop=stop), _stop_once_polling()
        )


async def test_supervisor_cancellation_drains_workers() -> None:
    # Arrange — the lifespan path: no stop event; the supervisor runs as a task and is cancelled on
    # shutdown. It must drain its workers and re-raise the cancellation (the lifespan suppresses
    # it), never leaving an orphaned worker task behind.
    queue = _SignallingQueue()
    storage, events = InMemoryVideoStorage(), InMemoryRunEventStore()
    task = asyncio.create_task(_supervisor(queue, storage, events, count=2, stop=None))

    await queue.first_poll.wait()  # the workers are up and polling
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_supervisor_floors_worker_count_to_one() -> None:
    # Arrange — a misconfigured count=0 must still drain the queue (one worker), never stall it.
    queue = _SignallingQueue(expected=1)
    storage, events = InMemoryVideoStorage(), InMemoryRunEventStore()
    await queue.enqueue(_job(0))
    stop = asyncio.Event()

    async def _stop_when_drained() -> None:
        await queue.all_settled.wait()
        stop.set()

    # Act + Assert — count=0 floors to 1 worker; the job reaches READY and the supervisor returns.
    async with asyncio.timeout(10):
        await asyncio.gather(
            _supervisor(queue, storage, events, count=0, stop=stop), _stop_when_drained()
        )
    job = await queue.get(job_id="job-0")
    assert job is not None and job.status == VideoJobStatus.READY


class _RecoverySignalQueue(InMemoryVideoJobQueue):
    """Fires ``recovered`` when a job settles READY — so the sweep-recovery test waits on the real
    completion event (which arrives only via sweep → requeue → claim → complete), not a sleep."""

    def __init__(self, *, clock: Any) -> None:
        super().__init__(clock=clock)
        self.recovered = asyncio.Event()

    async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None:
        await super().complete(job_id=job_id, contract_hash=contract_hash)
        self.recovered.set()


async def test_supervisor_sweep_recovers_a_job_a_dead_worker_left_in_flight() -> None:
    # Arrange — a job claimed at 10:00 by a worker that died; an injected clock pins "now" to 10:10,
    # so the lease (300s) is exceeded and the supervisor sweep should requeue it for a fresh claim.
    now = [datetime(2026, 6, 14, 10, 0, 0, tzinfo=UTC)]
    queue = _RecoverySignalQueue(clock=lambda: now[0])
    storage, events = InMemoryVideoStorage(), InMemoryRunEventStore()
    await queue.enqueue(_job(0))
    dead = await queue.claim(worker_id="dead-worker")  # status=planning, claimed_at=10:00
    assert dead is not None and dead.status == VideoJobStatus.PLANNING
    now[0] = datetime(2026, 6, 14, 10, 10, 0, tzinfo=UTC)
    stop = asyncio.Event()

    async def _stop_when_recovered() -> None:
        await queue.recovered.wait()  # only set once the requeued job is re-claimed + completed
        stop.set()

    # Act — the lease sweep requeues the stuck job; a live worker then claims + renders it.
    async with asyncio.timeout(10):
        await asyncio.gather(
            run_video_workers(
                queue=queue,
                pipeline=StubVideoPipeline(),
                storage=storage,
                events=events,
                count=1,
                poll_interval_seconds=0.01,
                worker_id_prefix="test",
                lease_seconds=300,
                lease_max_attempts=3,
                sweep_interval_seconds=0.01,
                stop=stop,
            ),
            _stop_when_recovered(),
        )

    # Assert — the orphaned job was recovered all the way to READY.
    job = await queue.get(job_id="job-0")
    assert job is not None and job.status == VideoJobStatus.READY
