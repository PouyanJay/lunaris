import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lunaris_covers import run_cover_workers
from lunaris_runtime.logging import configure_logging
from lunaris_video import run_video_workers

from .config import get_settings
from .dependencies import (
    get_course_store,
    get_cover_credential_resolver,
    get_cover_job_queue,
    get_cover_pipeline,
    get_cover_storage,
    get_run_event_store,
    get_video_credential_resolver,
    get_video_job_queue,
    get_video_pipeline,
    get_video_storage,
)
from .routers import (
    activity,
    admin_users,
    app_config,
    authorities,
    bookmarks,
    bridge,
    briefs,
    capabilities,
    corpus,
    courses,
    covers,
    credentials,
    explain,
    health,
    keyless,
    me,
    prod_ops,
    progress,
    runs,
    signup_gate,
    videos,
)
from .routers import settings as settings_router

_logger = structlog.get_logger()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the in-process video + cover workers for the app's lifetime (plan §1.1: locally each
    worker runs inside the API process; in cloud the same loop ships as its own container).

    Settings come from the environment directly (not request DI — there is no request here); the
    queue/storage getters resolve to the same process singletons request handlers see, so an
    enqueue over HTTP is visible to these workers.

    Each worker has two independent gates: a ``*_generation_enabled`` operator kill-switch (also
    what lets the API enqueue) and a ``*_inproc_worker_enabled`` flag (whether THIS process also
    drains the queue). Locally (``make run``) both are on — one process enqueues + renders. In cloud
    the API keeps enqueue on but turns the in-process worker OFF (app.bicep), so it never competes
    with the dedicated worker container — without that gate the API's stub-pipeline workers would
    race the real worker and settle jobs with placeholder media.

    Each pool is supervised by its shared ``run_*_workers`` spawn-N + drain-on-stop coroutine — the
    exact same one the standalone worker container runs, so there is one worker code path, never a
    fork. Here they run as background tasks cancelled on shutdown; the containers run them under a
    SIGTERM-wired stop event. ``{video,cover}_workers_started/stopped`` log from inside them.
    """
    settings = get_settings()
    supervisors: list[asyncio.Task[None]] = []
    if settings.video_generation_enabled and settings.video_inproc_worker_enabled:
        supervisors.append(
            asyncio.create_task(
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
        )
    if settings.cover_generation_enabled and settings.cover_inproc_worker_enabled:
        supervisors.append(
            asyncio.create_task(
                run_cover_workers(
                    queue=get_cover_job_queue(settings),
                    pipeline=get_cover_pipeline(settings),
                    storage=get_cover_storage(settings),
                    course_store=get_course_store(settings),
                    count=settings.cover_worker_count,
                    poll_interval_seconds=settings.cover_worker_poll_seconds,
                    worker_id_prefix=f"api-cover-{os.getpid()}",
                    credential_resolver=get_cover_credential_resolver(settings),
                    lease_seconds=settings.cover_lease_seconds,
                )
            )
        )
    yield
    # Cancel each supervisor; it cancels + drains its workers in turn. A job mid-render at shutdown
    # stays claimed (not settled); the lease-expiry/requeue sweep re-queues it.
    for supervisor in supervisors:
        supervisor.cancel()
    for supervisor in supervisors:
        with contextlib.suppress(asyncio.CancelledError):
            await supervisor


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(signup_gate.router)
    app.include_router(admin_users.router)
    app.include_router(prod_ops.router)
    app.include_router(courses.router)
    app.include_router(briefs.router)
    app.include_router(runs.router)
    app.include_router(bridge.router)
    app.include_router(settings_router.router)
    app.include_router(explain.router)
    app.include_router(corpus.router)
    app.include_router(authorities.router)
    app.include_router(progress.router)
    app.include_router(activity.router)
    app.include_router(bookmarks.router)
    app.include_router(app_config.router)
    app.include_router(credentials.router)
    app.include_router(capabilities.router)
    app.include_router(keyless.router)
    app.include_router(videos.router)
    app.include_router(covers.router)


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
