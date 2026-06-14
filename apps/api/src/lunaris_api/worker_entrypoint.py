"""Standalone entry point for the dedicated video-worker container (explainer-video V7).

In cloud the video worker ships as its own Azure Container App with the Manim render toolchain baked
in (Dockerfile.worker / infra/video.bicep), so CPU-bound renders never share a replica with
latency-sensitive API/SSE traffic (plan §1.1). It runs the **same** worker loop the API lifespan
runs in-process — composed from the **same** ``dependencies.py`` (queue, pipeline, storage, events),
so there is zero drift between the two deployments — supervised by the shared ``run_video_workers``.

Shutdown is cooperative: SIGTERM/SIGINT (ACA sends SIGTERM before stopping a replica) set a stop
event; the supervisor then cancels and drains its workers. A job mid-render at that point stays
PLANNING for the lease-expiry requeue sweep (V7), so a scale-in loses at most the scene in flight.

The worker does **not** check ``VIDEO_GENERATION_ENABLED`` — the operator flag gates enqueue on the
API side, and the KEDA scaler keys off the pending-job count, so the container only ever runs when
there are jobs to drain (and there are jobs only when the flag is on). Run: ``python -m
lunaris_api.worker_entrypoint``.
"""

import asyncio
import contextlib
import os
import signal

import structlog
from lunaris_runtime.logging import configure_logging
from lunaris_video import run_video_workers

from .config import get_settings
from .dependencies import (
    get_run_event_store,
    get_video_credential_resolver,
    get_video_job_queue,
    get_video_pipeline,
    get_video_storage,
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
        "video_worker_container_starting",
        worker_count=settings.video_worker_count,
        poll_seconds=settings.video_worker_poll_seconds,
    )
    await run_video_workers(
        queue=get_video_job_queue(settings),
        pipeline=get_video_pipeline(settings),
        storage=get_video_storage(settings),
        events=get_run_event_store(settings),
        count=settings.video_worker_count,
        poll_interval_seconds=settings.video_worker_poll_seconds,
        worker_id_prefix=f"worker-{os.getpid()}",
        credential_resolver=get_video_credential_resolver(settings),
        lease_seconds=settings.video_lease_seconds,
        stop=stop,
    )
    _logger.info("video_worker_container_stopped")


def main() -> None:
    """Boot structured logging and drain the video-job queue until SIGTERM/SIGINT."""
    configure_logging(json_output=True)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
