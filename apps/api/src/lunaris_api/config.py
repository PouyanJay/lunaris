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

    ``pipeline`` selects the course-generation backend: ``agent`` (the real deep-agent harness,
    needs ``ANTHROPIC_API_KEY``), ``live`` (the legacy single-shot orchestrator, also needs a key),
    or ``stub`` (deterministic, offline — for demos/tests).
    """

    pipeline: str
    course_dir: Path
    cors_origins: tuple[str, ...]
    secrets_path: Path
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None

    @property
    def has_supabase(self) -> bool:
        """Whether Supabase service-role creds are present (selects the durable run history)."""
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    origins = os.getenv("LUNARIS_CORS_ORIGINS", _DEFAULT_ORIGINS)
    return Settings(
        pipeline=os.getenv("LUNARIS_PIPELINE", "live").lower(),
        course_dir=Path(os.getenv("LUNARIS_COURSE_DIR", ".courses")),
        cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        secrets_path=Path(os.getenv("LUNARIS_SECRETS_PATH", ".secrets/secrets.json")),
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None,
    )
