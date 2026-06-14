"""Video V4-T3: the worker pool — N in-process workers drain one shared queue in parallel, and all
their Claude calls pace through one process-wide rate-limit token-bucket (plan §1.1 / §V4-T3).

Parallelism is what bounds the build's wall-time delta: with N workers, K queued videos drain in
~K/N waves rather than serially. Proven deterministically (no wall-clock) by holding every render
open until two are observed in flight at once.
"""

import asyncio
import contextlib

from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
)
from lunaris_runtime.resilience import get_llm_rate_limiter
from lunaris_runtime.schema import VideoJob, VideoKind
from lunaris_video import RenderedVideo, StubVideoPipeline, VideoWorker

_OWNER = "00000000-0000-0000-0000-000000000001"


class _GatedPipeline:
    """Wraps the stub pipeline but holds every render open on ``release``, tracking how many run at
    once — so a test can observe genuine parallelism before letting them finish. ``reached_target``
    fires the moment ``target`` renders are in flight together (no busy-wait poll needed)."""

    def __init__(self, release: asyncio.Event, *, target: int) -> None:
        self._inner = StubVideoPipeline()
        self._release = release
        self._target = target
        self.in_flight_count = 0
        self.peak = 0
        self.reached_target = asyncio.Event()

    async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
        self.in_flight_count += 1
        self.peak = max(self.peak, self.in_flight_count)
        if self.in_flight_count >= self._target:
            self.reached_target.set()
        try:
            await self._release.wait()  # held open by the test's outer timeout, not a local one
        finally:
            self.in_flight_count -= 1
        return await self._inner.produce(job)


def _job(index: int) -> VideoJob:
    return VideoJob(
        id=f"job-{index}",
        user_id=_OWNER,
        course_id="c1",
        lesson_id=f"l{index}",
        kind=VideoKind.LESSON,
        input_hash="h",
    )


async def test_n_workers_drain_the_queue_in_parallel() -> None:
    # Arrange — three queued jobs, two workers over one shared queue, every render held open.
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    for index in range(3):
        await queue.enqueue(_job(index))
    release = asyncio.Event()
    pipeline = _GatedPipeline(release, target=2)
    workers = [
        VideoWorker(
            queue=queue, pipeline=pipeline, storage=storage, events=events, worker_id=f"w{n}"
        )
        for n in range(2)
    ]
    tasks = [asyncio.create_task(w.run_forever(poll_interval_seconds=0.01)) for w in workers]

    # Act — wait until two renders are in flight at the same time (the second worker proves parallel
    # drain), then release them. The timeout fails fast if only one worker ever claims a job.
    try:
        async with asyncio.timeout(5):
            await pipeline.reached_target.wait()
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # Assert — two jobs rendered concurrently (SKIP-LOCKED claims never double-served the same job).
    assert pipeline.peak >= 2


async def test_two_workers_never_claim_the_same_job() -> None:
    # Arrange — one job, two workers polling.
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    await queue.enqueue(_job(0))
    workers = [
        VideoWorker(
            queue=queue,
            pipeline=StubVideoPipeline(),
            storage=storage,
            events=events,
            worker_id=f"w{n}",
        )
        for n in range(2)
    ]

    # Act — both run once; the queue's claim is mutually exclusive, so only one gets the job.
    results = await asyncio.gather(*(w.run_once() for w in workers))

    # Assert — exactly one worker processed it; the job settled once.
    assert sorted(results) == [False, True]
    job = await queue.get(job_id="job-0")
    assert job is not None and job.status.value == "ready"
    assert job.attempts == 1  # claimed exactly once, never double-served


def test_claude_calls_share_one_process_rate_limit_bucket() -> None:
    # The process-wide token-bucket: one instance on every call. The video pipeline's plan/codegen/
    # QA calls go through ``build_chat_model``, which wires this same limiter — so concurrent video
    # jobs pace ALL their Claude calls under one org budget, never N independent ones (plan §1.1).
    assert get_llm_rate_limiter() is get_llm_rate_limiter()
