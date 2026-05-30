import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DEFAULT_ORIGINS = (
    "http://localhost:5173,http://localhost:4173,http://localhost:4174,"
    "http://localhost:4175,http://localhost:4176"
)


@dataclass(frozen=True)
class Settings:
    """API runtime configuration, read from the environment.

    ``pipeline`` selects the course-generation backend: ``live`` (real Claude subagents,
    needs ``ANTHROPIC_API_KEY``) or ``stub`` (deterministic, offline — for demos/tests).
    """

    pipeline: str
    course_dir: Path
    cors_origins: tuple[str, ...]


@lru_cache
def get_settings() -> Settings:
    origins = os.getenv("LUNARIS_CORS_ORIGINS", _DEFAULT_ORIGINS)
    return Settings(
        pipeline=os.getenv("LUNARIS_PIPELINE", "live").lower(),
        course_dir=Path(os.getenv("LUNARIS_COURSE_DIR", ".courses")),
        cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
    )
