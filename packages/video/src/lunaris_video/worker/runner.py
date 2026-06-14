import asyncio
import contextlib

import structlog
from lunaris_runtime.persistence import IRunEventStore, IVideoJobQueue, IVideoStorage

from lunaris_video.protocols.video_pipeline_protocol import IVideoPipeline
from lunaris_video.worker.video_worker import VideoWorker

_logger = structlog.get_logger(__name__)


async def run_video_workers(
    *,
    queue: IVideoJobQueue,
    pipeline: IVideoPipeline,
    storage: IVideoStorage,
    events: IRunEventStore,
    count: int,
    poll_interval_seconds: float,
    worker_id_prefix: str,
    stop: asyncio.Event | None = None,
) -> None:
    """Spawn ``count`` workers draining one shared queue; run until cancelled or ``stop`` is set.

    The single supervisor both deployments use (plan §1.1): the API lifespan starts it as a
    background task and **cancels** it on shutdown; the standalone worker container runs it under
    ``asyncio.run`` with a ``stop`` event wired to SIGTERM/SIGINT. Either way, on exit it cancels
    and drains the worker tasks so a clean shutdown never orphans one — a job mid-render stays
    PLANNING (claimed, not settled) for the lease-expiry requeue sweep (V7), so no work is lost
    silently. ``count`` is floored at 1 (a misconfigured 0 would stall the queue forever).

    The workers share the passed queue/pipeline/storage/events: SKIP-LOCKED claims mean two never
    get the same job, so renders overlap; ``worker_id_prefix`` distinguishes them in the logs.
    """
    workers = [
        VideoWorker(
            queue=queue,
            pipeline=pipeline,
            storage=storage,
            events=events,
            worker_id=f"{worker_id_prefix}-{index}",
        )
        for index in range(max(1, count))
    ]
    tasks = [
        asyncio.create_task(worker.run_forever(poll_interval_seconds=poll_interval_seconds))
        for worker in workers
    ]
    _logger.info("video_workers_started", count=len(tasks), poll_seconds=poll_interval_seconds)
    try:
        if stop is None:
            # Lifespan path: workers never return on their own (run_forever absorbs every job
            # error), so gather blocks until this supervisor coroutine is cancelled on shutdown.
            await asyncio.gather(*tasks)
        else:
            # Container path: the workers never complete on their own, so race them against the
            # stop signal — it firing is what ends the wait; the finally then drains the workers.
            stop_waiter = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait({*tasks, stop_waiter}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                stop_waiter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stop_waiter
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        _logger.info("video_workers_stopped", count=len(tasks))
