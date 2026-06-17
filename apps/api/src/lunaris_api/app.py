import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    signup_gate,
    videos,
)
from .routers import settings as settings_router

_logger = structlog.get_logger()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the in-process video worker for the app's lifetime (plan §1.1: locally the worker runs
    inside the API process; in cloud the same loop ships as its own container — V7).

    Settings come from the environment directly (not request DI — there is no request here); the
    queue/storage getters resolve to the same process singletons request handlers see, so an
    enqueue over HTTP is visible to this worker.

    Two independent gates: ``video_generation_enabled`` is the operator kill-switch (also what lets
    the API enqueue); ``video_inproc_worker_enabled`` is whether THIS process also drains the queue.
    Locally (``make run``) both are on — one process enqueues + renders. In cloud the API keeps
    enqueue on but turns the in-process worker OFF (app.bicep), so it never competes with the
    dedicated worker container — without that gate the API's stub-pipeline workers (the lean API
    image has no Manim) would race the real worker and settle jobs with placeholder media.

    The worker pool is supervised by the shared ``run_video_workers`` (V7-T0) — the exact same
    spawn-N + drain-on-stop coroutine the standalone worker container runs, so there is one worker
    code path, never a fork. Here it runs as a background task cancelled on shutdown; the container
    runs it under a SIGTERM-wired stop event. ``video_workers_started/stopped`` log from inside it.
    """
    settings = get_settings()
    supervisor: asyncio.Task[None] | None = None
    if settings.video_generation_enabled and settings.video_inproc_worker_enabled:
        supervisor = asyncio.create_task(
            run_video_workers(
                queue=get_video_job_queue(settings),
                pipeline=get_video_pipeline(settings),
                storage=get_video_storage(settings),
                events=get_run_event_store(settings),
                count=settings.video_worker_count,
                poll_interval_seconds=settings.video_worker_poll_seconds,
                worker_id_prefix=f"api-{os.getpid()}",
                credential_resolver=get_video_credential_resolver(settings),
                lease_seconds=settings.video_lease_seconds,
            )
        )
    yield
    # Cancel the supervisor; it cancels + drains its workers in turn. A job mid-render at shutdown
    # stays PLANNING (claimed, not settled); the lease-expiry/requeue sweep (V7) re-queues it.
    if supervisor is not None:
        supervisor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await supervisor


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(signup_gate.router)
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
        # The SPA reads these off responses; cross-origin (app vs api subdomain) they must be
        # exposed or the browser hides them. X-Course-Id lets a dropped build stream re-attach.
        expose_headers=["X-Run-Id", "X-Course-Id", "X-Request-Id"],
    )
    _register_routers(app)
    return app
