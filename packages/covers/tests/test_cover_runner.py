"""run_cover_workers supervisor contract (course-cover-images T6).

The supervisor both deployments share: it spawns N workers over one queue plus a lease sweep, drains
enqueued jobs, and shuts down cleanly when its ``stop`` event fires (the container path) — mirroring
``run_video_workers``.
"""

import asyncio

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


async def test_supervisor_drains_the_queue_then_stops_on_signal() -> None:
    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    course_store = _FakeCourseStore()
    for i in (1, 2, 3):
        course_store.seed(Course(id=f"c{i}", topic=f"topic {i}"), owner_id=_OWNER)
        await queue.enqueue(
            CoverJob(id=f"job-{i}", user_id=_OWNER, course_id=f"c{i}", input_hash="h")
        )

    stop = asyncio.Event()
    supervisor = asyncio.create_task(
        run_cover_workers(
            queue=queue,
            pipeline=StubCoverPipeline(),
            storage=storage,
            course_store=course_store,  # type: ignore[arg-type]
            count=2,
            poll_interval_seconds=0.01,
            worker_id_prefix="test",
            sweep_interval_seconds=5.0,
            stop=stop,
        )
    )

    # Wait until all three jobs have settled READY, then signal stop.
    for _ in range(500):
        jobs = [await queue.get(job_id=f"job-{i}") for i in (1, 2, 3)]
        if all(j is not None and j.status is CoverJobStatus.READY for j in jobs):
            break
        await asyncio.sleep(0.01)
    stop.set()

    # The supervisor drains its tasks and returns cleanly (no orphaned task, no raise).
    await asyncio.wait_for(supervisor, timeout=2)
    for i in (1, 2, 3):
        job = await queue.get(job_id=f"job-{i}")
        assert job is not None and job.status is CoverJobStatus.READY


async def test_supervisor_floors_worker_count_at_one() -> None:
    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    course_store = _FakeCourseStore()
    course_store.seed(Course(id="c1", topic="t"), owner_id=_OWNER)
    await queue.enqueue(CoverJob(id="job-1", user_id=_OWNER, course_id="c1", input_hash="h"))

    stop = asyncio.Event()
    supervisor = asyncio.create_task(
        run_cover_workers(
            queue=queue,
            pipeline=StubCoverPipeline(),
            storage=storage,
            course_store=course_store,  # type: ignore[arg-type]
            count=0,  # misconfigured — must still drain (floored to 1), not stall forever
            poll_interval_seconds=0.01,
            worker_id_prefix="test",
            sweep_interval_seconds=5.0,
            stop=stop,
        )
    )
    for _ in range(500):
        job = await queue.get(job_id="job-1")
        if job is not None and job.status is CoverJobStatus.READY:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(supervisor, timeout=2)
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status is CoverJobStatus.READY
