from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lunaris_runtime.logging import configure_logging

from .config import get_settings
from .routers import courses, health


def create_app() -> FastAPI:
    """Build the Lunaris API: structured logging, CORS for the web client, and the routers."""
    configure_logging(json_output=True)
    settings = get_settings()

    app = FastAPI(title="Lunaris API", version="0.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-Run-Id"],
    )
    app.include_router(health.router)
    app.include_router(courses.router)
    return app
