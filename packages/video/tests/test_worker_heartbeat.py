"""Video V7-T4: the worker heartbeats while it renders, so the lease-timeout sweep can tell a live
worker from a dead one. Proven by holding a render open and observing a real heartbeat fire against
the queue before letting it finish — no sleeps as synchronisation."""

import asyncio

from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
)
from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind
from lunaris_video import RenderedVideo, StubVideoPipeline, VideoWorker

_OWNER = "00000000-0000-0000-0000-000000000001"


def _job() -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id=_OWNER,
        course_id="c1",
        lesson_id="l1",
        kind=VideoKind.LESSON,
        input_hash="h",
    )


class _HeartbeatRecordingQueue(InMemoryVideoJobQueue):
    """Counts heartbeats and signals the first one — so the test waits on a real heartbeat, not a
    sleep, while the render is held open."""

    def __init__(self) -> None:
        super().__init__()
        self.heartbeats = 0
        self.beat = asyncio.Event()

    async def heartbeat(self, *, job_id: str) -> None:
        await super().heartbeat(job_id=job_id)
        self.heartbeats += 1
        self.beat.set()


class _HeldRenderPipeline:
    """Blocks produce until ``release`` is set, so the test can observe a heartbeat mid-render."""

    def __init__(self, release: asyncio.Event) -> None:
        self._release = release
        self._inner = StubVideoPipeline()

    async def produce(self, job: VideoJob) -> RenderedVideo:
        await self._release.wait()
        return await self._inner.produce(job)


async def test_worker_heartbeats_while_a_render_is_in_flight() -> None:
    # Arrange — a job, a render held open, a tiny heartbeat interval.
    queue = _HeartbeatRecordingQueue()
    storage, events = InMemoryVideoStorage(), InMemoryRunEventStore()
    await queue.enqueue(_job())
    release = asyncio.Event()
    worker = VideoWorker(
        queue=queue,
        pipeline=_HeldRenderPipeline(release),
        storage=storage,
        events=events,
        worker_id="w",
        heartbeat_interval_s=0.01,
    )

    # Act — process the job; while produce is blocked, the heartbeat loop must fire at least once.
    task = asyncio.create_task(worker.run_once())
    try:
        async with asyncio.timeout(5):
            await queue.beat.wait()  # a real heartbeat landed during the render
    finally:
        release.set()  # let produce finish so the worker settles + cancels the heartbeat
        await task

    # Assert — the lease was extended mid-render, and the job still settles READY cleanly.
    assert queue.heartbeats >= 1
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.READY
