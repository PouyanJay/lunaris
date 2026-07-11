"""run_cover_workers supervisor contract (course-cover-images T6).

The supervisor both deployments share: it spawns N workers over one queue plus a lease sweep, drains
enqueued jobs, recovers a job a dead worker abandoned mid-render, and shuts down cleanly when its
``stop`` event fires (the container path) — mirroring ``run_video_workers``. Synchronisation is
event-based (a settle signal + an injected clock), never sleep-polling.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from lunaris_covers import StubCoverPipeline, run_cover_workers
from lunaris_runtime.persistence import InMemoryCoverJobQueue, InMemoryCoverStorage
from lunaris_runtime.schema import Course, CoverJob, CoverJobStatus

_OWNER = "u1"


class _FakeCourseStore:
    def __init__(self) -> None:
        self._by_owner: dict[tuple[str | None, str], Course] = {}

    def seed(self, course: Course, *, owner_id: str) -> None:
        self._by_owner[(owner_id, course.id)] = course

    def save(self, course: Course, *, owner_id: str | None = None) -> None:
        self._by_owner[(owner_id, course.id)] = course

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        course = self._by_owner.get((owner_id, course_id))
        if course is None:
            raise FileNotFoundError(course_id)
        return course

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return self._by_owner.pop((owner_id, course_id), None) is not None


class _SettleSignalQueue(InMemoryCoverJobQueue):
    """Fires ``all_settled`` (an event, not a sleep-poll) once ``target`` jobs have completed
    READY — so a supervisor test waits deterministically on the drain instead of polling."""

    def __init__(self, *, target: int, clock=None) -> None:
        super().__init__(clock=clock)
        self._target = target
        self._settled = 0
        self.all_settled = asyncio.Event()

    async def complete(self, *, job_id: str) -> None:
        await super().complete(job_id=job_id)
        self._settled += 1
        if self._settled >= self._target:
            self.all_settled.set()


def _supervisor(
    queue: InMemoryCoverJobQueue,
    storage: InMemoryCoverStorage,
    course_store: _FakeCourseStore,
    stop: asyncio.Event,
    *,
    count: int,
    lease_seconds: int = 300,
    sweep_interval_seconds: float = 5.0,
) -> asyncio.Task[None]:
    return asyncio.create_task(
        run_cover_workers(
            queue=queue,
            pipeline=StubCoverPipeline(),
            storage=storage,
            course_store=course_store,  # type: ignore[arg-type]
            count=count,
            poll_interval_seconds=0.01,
            worker_id_prefix="test",
            lease_seconds=lease_seconds,
            sweep_interval_seconds=sweep_interval_seconds,
            stop=stop,
        )
    )


async def _drain_and_stop(supervisor: asyncio.Task[None], stop: asyncio.Event) -> None:
    stop.set()
    await asyncio.wait_for(supervisor, timeout=2)


async def test_supervisor_drains_the_queue_then_stops_on_signal() -> None:
    queue, storage = _SettleSignalQueue(target=3), InMemoryCoverStorage()
    course_store = _FakeCourseStore()
    for i in (1, 2, 3):
        course_store.seed(Course(id=f"c{i}", topic=f"topic {i}"), owner_id=_OWNER)
        await queue.enqueue(
            CoverJob(id=f"job-{i}", user_id=_OWNER, course_id=f"c{i}", input_hash="h")
        )

    stop = asyncio.Event()
    supervisor = _supervisor(queue, storage, course_store, stop, count=2)

    await asyncio.wait_for(queue.all_settled.wait(), timeout=2)
    await _drain_and_stop(supervisor, stop)

    for i in (1, 2, 3):
        job = await queue.get(job_id=f"job-{i}")
        assert job is not None and job.status is CoverJobStatus.READY


async def test_supervisor_floors_worker_count_at_one() -> None:
    queue, storage = _SettleSignalQueue(target=1), InMemoryCoverStorage()
    course_store = _FakeCourseStore()
    course_store.seed(Course(id="c1", topic="t"), owner_id=_OWNER)
    await queue.enqueue(CoverJob(id="job-1", user_id=_OWNER, course_id="c1", input_hash="h"))

    stop = asyncio.Event()
    # count=0 is misconfigured — the supervisor must still drain (floored to 1), not stall forever.
    supervisor = _supervisor(queue, storage, course_store, stop, count=0)

    await asyncio.wait_for(queue.all_settled.wait(), timeout=2)
    await _drain_and_stop(supervisor, stop)

    job = await queue.get(job_id="job-1")
    assert job is not None and job.status is CoverJobStatus.READY


async def test_supervisor_sweep_recovers_a_job_a_dead_worker_left_in_flight() -> None:
    # Arrange — a job claimed at 10:00 by a worker that then died; an injected clock pins "now" to
    # 10:10, past the 60s lease, so the supervisor's sweep must requeue it for a live worker. This
    # guards the exact lease-recovery mechanism the KEDA scaler + sweep exist for.
    now = [datetime(2026, 1, 1, 10, 0, tzinfo=UTC)]
    queue = _SettleSignalQueue(target=1, clock=lambda: now[0])
    storage = InMemoryCoverStorage()
    course_store = _FakeCourseStore()
    course_store.seed(Course(id="c1", topic="t"), owner_id=_OWNER)
    await queue.enqueue(CoverJob(id="job-1", user_id=_OWNER, course_id="c1", input_hash="h"))
    dead = await queue.claim(worker_id="dead-worker")  # claimed + leased, then the worker vanishes
    assert dead is not None and dead.status is not CoverJobStatus.QUEUED
    now[0] = now[0] + timedelta(seconds=610)  # advance well past the lease window

    stop = asyncio.Event()
    supervisor = _supervisor(
        queue, storage, course_store, stop, count=1, lease_seconds=60, sweep_interval_seconds=0.01
    )

    # Assert — the sweep requeued the abandoned job and a live worker re-claimed + finished it.
    await asyncio.wait_for(queue.all_settled.wait(), timeout=2)
    await _drain_and_stop(supervisor, stop)

    job = await queue.get(job_id="job-1")
    assert job is not None and job.status is CoverJobStatus.READY
