import asyncio
import contextlib

import structlog
from lunaris_runtime.credentials import CredentialResolver
from lunaris_runtime.persistence import (
    ICourseStore,
    ICoverJobQueue,
    ICoverStorage,
    PersistenceError,
)

from lunaris_covers.protocols.cover_pipeline_protocol import ICoverPipeline
from lunaris_covers.worker.cover_worker import CoverWorker

_logger = structlog.get_logger(__name__)


async def run_cover_workers(
    *,
    queue: ICoverJobQueue,
    pipeline: ICoverPipeline,
    storage: ICoverStorage,
    course_store: ICourseStore,
    count: int,
    poll_interval_seconds: float,
    worker_id_prefix: str,
    credential_resolver: CredentialResolver | None = None,
    lease_seconds: int = 300,
    lease_max_attempts: int = 3,
    sweep_interval_seconds: float = 60.0,
    heartbeat_interval_s: float = 60.0,
    stop: asyncio.Event | None = None,
) -> None:
    """Spawn ``count`` cover workers draining one shared queue (plus a lease sweep); run until
    cancelled or ``stop`` is set. The exact shape of ``run_video_workers`` for covers.

    The single supervisor both deployments use: the API lifespan starts it as a background task and
    **cancels** it on shutdown; the standalone worker container runs it under ``asyncio.run`` with
    a ``stop`` event wired to SIGTERM/SIGINT. Either way, on exit it cancels and drains every task
    so a clean shutdown never orphans one. ``count`` is floored at 1 (a misconfigured 0 stalls the
    queue forever).

    The workers share the passed queue/pipeline/storage/course_store: SKIP-LOCKED claims mean two
    never get the same job, so renders overlap; ``worker_id_prefix`` distinguishes them in the
    logs. The optional ``credential_resolver`` (the cloud worker's BYOK vault resolver) renders
    each job on its owner's OpenAI/Anthropic keys — see ``CoverWorker``.

    Alongside the workers runs ONE lease sweep: every ``sweep_interval_seconds`` it requeues jobs a
    dead worker left in-flight past ``lease_seconds`` (a live render heartbeats, so its lease stays
    fresh) and dead-letters those past ``lease_max_attempts``. Running it in every replica is safe
    (the sweep is atomic + idempotent); the KEDA scaler counts stale in-flight rows too, so a job
    stuck after a scale-to-zero still wakes a replica that sweeps and re-claims it."""
    workers = [
        CoverWorker(
            queue=queue,
            pipeline=pipeline,
            storage=storage,
            course_store=course_store,
            worker_id=f"{worker_id_prefix}-{index}",
            credential_resolver=credential_resolver,
            heartbeat_interval_s=heartbeat_interval_s,
        )
        for index in range(max(1, count))
    ]
    worker_tasks = [
        asyncio.create_task(worker.run_forever(poll_interval_seconds=poll_interval_seconds))
        for worker in workers
    ]
    sweep_task = asyncio.create_task(
        _sweep_leases_forever(
            queue,
            lease_seconds=lease_seconds,
            max_attempts=lease_max_attempts,
            interval_seconds=sweep_interval_seconds,
        )
    )
    tasks = [*worker_tasks, sweep_task]
    _logger.info(
        "cover_workers_started", count=len(worker_tasks), poll_seconds=poll_interval_seconds
    )
    try:
        if stop is None:
            # Lifespan path: the tasks never return on their own, so gather blocks until this
            # supervisor coroutine is cancelled on shutdown.
            await asyncio.gather(*tasks)
        else:
            # Container path: the tasks never complete on their own, so race them against the stop
            # signal — it firing is what ends the wait; the finally then drains the tasks.
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
        _logger.info("cover_workers_stopped", count=len(worker_tasks))


async def _sweep_leases_forever(
    queue: ICoverJobQueue, *, lease_seconds: int, max_attempts: int, interval_seconds: float
) -> None:
    """Sweep stale leases now and every ``interval_seconds`` after, until cancelled. Sweep-then-
    sleep so a freshly-woken replica recovers stuck jobs immediately. A sweep failure is logged, not
    fatal — the loop survives a transient queue blip."""
    while True:
        try:
            result = await queue.sweep_stale_leases(
                lease_seconds=lease_seconds, max_attempts=max_attempts
            )
            if result.requeued or result.dead_lettered:
                _logger.info(
                    "cover_worker.lease_sweep",
                    requeued=result.requeued,
                    dead_lettered=result.dead_lettered,
                )
        except PersistenceError:
            _logger.warning("cover_worker.lease_sweep_failed", exc_info=True)
        await asyncio.sleep(interval_seconds)
