from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lunaris_runtime.logging import configure_logging

from .config import get_settings
from .routers import courses, health, runs
from .routers import settings as settings_router


def create_app() -> FastAPI:
    """Build the Lunaris API: structured logging, CORS for the web client, and the routers."""
    configure_logging(json_output=True)
    settings = get_settings()

    app = FastAPI(title="Lunaris API", version="0.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        # The web uses GET (reads, SSE stream), POST (build a course), and PUT/DELETE (set/clear a
        # secret in the Settings panel). The browser preflights PUT/DELETE, so they must be allowed
        # or the preflight 400s and the fetch surfaces as a network error in the UI.
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Run-Id"],
    )
    app.include_router(health.router)
    app.include_router(courses.router)
    app.include_router(runs.router)
    app.include_router(settings_router.router)
    return app
