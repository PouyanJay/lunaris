"""Standalone entry point for the dedicated cover-worker container (course-cover-images).

In cloud the cover worker ships as its own Azure Container App (Dockerfile.cover / cover.bicep) so
cover-generation jobs never share a replica with latency-sensitive API/SSE traffic. It runs the
**same** worker loop the API lifespan runs in-process — composed from the **same**
``dependencies.py`` (queue, pipeline, storage, course store), so there is zero drift between the two
deployments — supervised by the shared ``run_cover_workers``.

Shutdown is cooperative: SIGTERM/SIGINT (ACA sends SIGTERM before stopping a replica) set a stop
event; the supervisor then cancels and drains its workers. A job mid-render at that point stays
in-flight for the lease-expiry requeue sweep, so a scale-in loses at most the cover in flight.

The worker does **not** check ``COVER_GENERATION_ENABLED`` — the operator flag gates enqueue on the
API side, and the KEDA scaler keys off the pending-job count, so the container only ever runs when
there are jobs to drain (and there are jobs only when the flag is on). Run: ``python -m
lunaris_api.cover_worker_entrypoint``.
"""

import asyncio
import contextlib
import os
import signal

import structlog
from lunaris_covers import run_cover_workers
from lunaris_runtime.logging import configure_logging

from .config import get_settings
from .dependencies import (
    get_course_store,
    get_cover_credential_resolver,
    get_cover_job_queue,
    get_cover_pipeline,
    get_cover_storage,
)

_logger = structlog.get_logger()


async def _run() -> None:
    settings = get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # add_signal_handler is unavailable on Windows; the container is Linux, so this always binds
        # there — the suppress only keeps a local non-Linux run from crashing on import-and-go.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    _logger.info(
        "cover_worker_container_starting",
        worker_count=settings.cover_worker_count,
        poll_seconds=settings.cover_worker_poll_seconds,
    )
    await run_cover_workers(
        queue=get_cover_job_queue(settings),
        pipeline=get_cover_pipeline(settings),
        storage=get_cover_storage(settings),
        course_store=get_course_store(settings),
        count=settings.cover_worker_count,
        poll_interval_seconds=settings.cover_worker_poll_seconds,
        worker_id_prefix=f"cover-{os.getpid()}",
        credential_resolver=get_cover_credential_resolver(settings),
        lease_seconds=settings.cover_lease_seconds,
        stop=stop,
    )
    _logger.info("cover_worker_container_stopped")


def main() -> None:
    """Boot structured logging and drain the cover-job queue until SIGTERM/SIGINT."""
    configure_logging(json_output=True)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
