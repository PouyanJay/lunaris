import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lunaris_runtime.logging import configure_logging
from lunaris_video import VideoWorker

from .config import get_settings
from .dependencies import (
    get_run_event_store,
    get_video_job_queue,
    get_video_pipeline,
    get_video_storage,
)
from .routers import (
    app_config,
    authorities,
    bridge,
    briefs,
    capabilities,
    corpus,
    courses,
    credentials,
    explain,
    health,
    keyless,
    me,
    runs,
    videos,
)
from .routers import settings as settings_router

_logger = structlog.get_logger()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the in-process video worker for the app's lifetime (plan §1.1: locally the worker runs
    inside the API process; in cloud the same loop ships as its own container in V7).

    Settings come from the environment directly (not request DI — there is no request here); the
    queue/storage getters resolve to the same process singletons request handlers see, so an
    enqueue over HTTP is visible to this worker. Gated by the operator kill-switch.
    """
    settings = get_settings()
    worker_tasks: list[asyncio.Task[None]] = []
    if settings.video_generation_enabled:
        # N in-process workers (plan §8.4) draining one shared queue — SKIP-LOCKED claims mean two
        # workers never get the same job, so renders overlap. The queue/pipeline/storage/events are
        # the same singletons request handlers see, shared across all workers; ids distinguish them.
        queue = get_video_job_queue(settings)
        pipeline = get_video_pipeline(settings)
        storage = get_video_storage(settings)
        run_event_store = get_run_event_store(settings)
        # Fail-open: a misconfigured 0 still gets one worker, never zero (which stalls all jobs).
        worker_count = max(1, settings.video_worker_count)
        for index in range(worker_count):
            worker = VideoWorker(
                queue=queue,
                pipeline=pipeline,
                storage=storage,
                events=run_event_store,
                worker_id=f"api-{os.getpid()}-{index}",
            )
            worker_tasks.append(
                asyncio.create_task(
                    worker.run_forever(poll_interval_seconds=settings.video_worker_poll_seconds)
                )
            )
        _logger.info(
            "video_workers_started",
            count=worker_count,
            poll_seconds=settings.video_worker_poll_seconds,
        )
    yield
    # Cancel all, then drain all — a job mid-render at shutdown stays PLANNING (claimed, not
    # settled); the lease-expiry/requeue sweep (V7) re-queues it, so no work is lost silently.
    for task in worker_tasks:
        task.cancel()
    for task in worker_tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if worker_tasks:
        _logger.info("video_workers_stopped", count=len(worker_tasks))


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(courses.router)
    app.include_router(briefs.router)
    app.include_router(runs.router)
    app.include_router(bridge.router)
    app.include_router(settings_router.router)
    app.include_router(explain.router)
    app.include_router(corpus.router)
    app.include_router(authorities.router)
    app.include_router(app_config.router)
    app.include_router(credentials.router)
    app.include_router(capabilities.router)
    app.include_router(keyless.router)
    app.include_router(videos.router)


def create_app() -> FastAPI:
    """Build the Lunaris API: structured logging, CORS for the web client, and the routers."""
    configure_logging(json_output=True)
    settings = get_settings()

    app = FastAPI(title="Lunaris API", version="0.0.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        # The web uses GET (reads, SSE stream), POST (build a course), and PUT/DELETE (set/clear a
        # secret in the Settings panel). The browser preflights PUT/DELETE, so they must be allowed
        # or the preflight 400s and the fetch surfaces as a network error in the UI.
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Run-Id", "X-Request-Id"],
    )
    _register_routers(app)
    return app
