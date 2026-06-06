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

    ``pipeline`` selects the course-generation backend and defaults to ``agent`` (the real
    deep-agent harness — the product default, needs ``ANTHROPIC_API_KEY``). The alternatives are
    ``live`` (the legacy single-shot orchestrator, also needs a key) and ``stub`` (deterministic,
    offline — for demos/tests). ``make run`` resolves this with a key guard, falling back to
    ``stub`` when no key is reachable; a direct ``uvicorn`` launch trusts the operator for a key.
    """

    pipeline: str
    course_dir: Path
    cors_origins: tuple[str, ...]
    # Single source of truth for operator secrets (see SecretStore).
    env_file: Path = Path(".env")
    config_path: Path = Path(".config/config.json")
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    embeddings_api_key: str | None = None

    @property
    def has_supabase(self) -> bool:
        """Whether Supabase service-role creds are present (selects the durable run history)."""
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def has_embeddings(self) -> bool:
        """Whether the embeddings key is present (the durable corpus needs it to ingest)."""
        return bool(self.embeddings_api_key)


@lru_cache
def get_settings() -> Settings:
    origins = os.getenv("LUNARIS_CORS_ORIGINS", _DEFAULT_ORIGINS)
    return Settings(
        pipeline=os.getenv("LUNARIS_PIPELINE", "agent").lower(),
        course_dir=Path(os.getenv("LUNARIS_COURSE_DIR", ".courses")),
        cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        env_file=Path(os.getenv("LUNARIS_ENV_FILE", ".env")),
        config_path=Path(os.getenv("LUNARIS_CONFIG_PATH", ".config/config.json")),
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None,
        embeddings_api_key=os.getenv("EMBEDDINGS_API_KEY") or None,
    )
