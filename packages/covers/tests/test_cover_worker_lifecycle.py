"""CoverWorker heartbeat + cancel-watcher contract (course-cover-images T6).

Mirrors the VideoWorker's V7 lease/cancel behaviour for covers: while a render runs the worker
heartbeats to keep its lease fresh (so the sweep can tell a live worker from a dead one), and an
owner stop (the job row going CANCELLED) aborts the render promptly — no compute wasted, nothing
uploaded, the job left terminal-CANCELLED and never settled READY/FAILED over the top.
"""

import asyncio

from lunaris_covers import CoverWorker, StubCoverPipeline
from lunaris_covers.models.rendered_cover import RenderedCover
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


class _HeartbeatSpyQueue(InMemoryCoverJobQueue):
    """An in-memory queue that counts heartbeat calls, to prove the render extends its lease."""

    def __init__(self) -> None:
        super().__init__()
        self.heartbeats = 0

    async def heartbeat(self, *, job_id: str) -> None:
        self.heartbeats += 1
        await super().heartbeat(job_id=job_id)


def _job(job_id: str = "job-1") -> CoverJob:
    return CoverJob(id=job_id, user_id=_OWNER, course_id="course-1", input_hash="h")


def _store() -> _FakeCourseStore:
    store = _FakeCourseStore()
    store.seed(Course(id="course-1", topic="How HTTP works"), owner_id=_OWNER)
    return store


async def test_heartbeat_fires_while_a_slow_render_runs() -> None:
    # Arrange — a render that blocks until released, and a fast heartbeat so ticks accrue.
    release = asyncio.Event()

    class _SlowPipeline:
        async def produce(self, job: CoverJob, *, on_stage) -> RenderedCover:
            await release.wait()
            return await StubCoverPipeline().produce(job, on_stage=on_stage)

    queue, storage = _HeartbeatSpyQueue(), InMemoryCoverStorage()
    await queue.enqueue(_job())
    worker = CoverWorker(
        queue=queue,
        pipeline=_SlowPipeline(),
        storage=storage,
        course_store=_store(),  # type: ignore[arg-type]
        worker_id="w",
        heartbeat_interval_s=0.01,
        cancel_poll_interval_s=5.0,
    )

    # Act — start the render, wait until the heartbeat has fired a couple of times, then release.
    run = asyncio.create_task(worker.run_once())
    for _ in range(500):
        if queue.heartbeats >= 2:
            break
        await asyncio.sleep(0.005)
    release.set()

    # Assert — the render completed READY, and the lease was heartbeated while it ran.
    assert await asyncio.wait_for(run, timeout=2) is True
    assert queue.heartbeats >= 2
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == CoverJobStatus.READY


async def test_owner_cancel_mid_render_aborts_without_uploading_or_settling() -> None:
    # Arrange — a render that hangs until its task is cancelled; the owner stops the job meanwhile.
    started = asyncio.Event()

    class _HangingPipeline:
        async def produce(self, job: CoverJob, *, on_stage) -> RenderedCover:
            await on_stage(CoverJobStatus.RENDERING)
            started.set()
            await asyncio.Event().wait()  # never returns — only cancellation ends it
            raise AssertionError("unreachable")

    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    course_store = _store()
    await queue.enqueue(_job())
    worker = CoverWorker(
        queue=queue,
        pipeline=_HangingPipeline(),
        storage=storage,
        course_store=course_store,  # type: ignore[arg-type]
        worker_id="w",
        heartbeat_interval_s=5.0,
        cancel_poll_interval_s=0.01,
    )

    # Act — once the render is in flight, the owner cancels; the watcher aborts the render.
    run = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(started.wait(), timeout=1)
    assert await queue.cancel(job_id="job-1", owner_id=_OWNER) is True
    assert await asyncio.wait_for(run, timeout=2) is True  # the loop never raises

    # Assert — terminal CANCELLED (not settled READY/FAILED), nothing uploaded, no cover attached.
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == CoverJobStatus.CANCELLED
    assert not any(p.endswith("/cover.png") for p in storage.paths())
    assert course_store.load("course-1", owner_id=_OWNER).cover is None
