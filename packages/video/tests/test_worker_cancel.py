"""Per-video STOP: the worker aborts an in-flight render the moment its owner cancels the job, so no
further compute is spent. Proven on the real worker loop — a render held open mid-flight, the job
flipped to CANCELLED through the real queue, and the worker observed cancelling the render task and
leaving the job CANCELLED (never settling it READY/FAILED, never uploading). No sleeps as
synchronisation: the test waits on the render actually starting, then on run_once returning."""

import asyncio

from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
)
from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind
from lunaris_video import RenderedVideo, VideoWorker

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


class _HeldRenderPipeline:
    """Blocks produce until the render task is cancelled — standing in for a long render the owner
    stops mid-flight. Records that it WAS cancelled (the compute actually stopped)."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.was_cancelled = False

    async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
        self.started.set()
        try:
            await asyncio.Event().wait()  # block forever — only a cancel ends this
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise
        raise AssertionError("the held render should only end via cancellation")


async def test_worker_aborts_an_in_flight_render_when_the_owner_cancels() -> None:
    # Arrange — a job whose render blocks, a tiny cancel-poll interval so the watcher notices fast.
    queue = InMemoryVideoJobQueue()
    storage, events = InMemoryVideoStorage(), InMemoryRunEventStore()
    await queue.enqueue(_job())
    pipeline = _HeldRenderPipeline()
    worker = VideoWorker(
        queue=queue,
        pipeline=pipeline,
        storage=storage,
        events=events,
        worker_id="w",
        cancel_poll_interval_s=0.01,
    )

    # Act — start processing; once the render is in flight, the owner stops the job. The worker's
    # cancel-watcher must abort the render and let run_once return.
    task = asyncio.create_task(worker.run_once())
    try:
        async with asyncio.timeout(5):
            await pipeline.started.wait()
            cancelled = await queue.cancel(job_id="job-1", owner_id=_OWNER)
            assert cancelled is True
            await task
    finally:
        if not task.done():
            task.cancel()

    # Assert — the render's compute was actually stopped, the job stayed CANCELLED (NOT settled
    # READY/FAILED), and no playable artifact was uploaded for a stopped video.
    assert pipeline.was_cancelled is True
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.CANCELLED
    assert storage.paths() == []  # nothing published


async def test_worker_never_claims_a_cancelled_queued_job() -> None:
    # Arrange — a job cancelled while still QUEUED (the common automatic-build case).
    queue = InMemoryVideoJobQueue()
    storage, events = InMemoryVideoStorage(), InMemoryRunEventStore()
    await queue.enqueue(_job())
    await queue.cancel(job_id="job-1", owner_id=_OWNER)
    worker = VideoWorker(
        queue=queue, pipeline=_HeldRenderPipeline(), storage=storage, events=events, worker_id="w"
    )

    # Act — a poll finds nothing claimable, so no compute is ever spent.
    processed = await worker.run_once()

    # Assert
    assert processed is False
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.CANCELLED
