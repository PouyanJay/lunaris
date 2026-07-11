import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from lunaris_runtime.device_bridge import BridgeLimits
from lunaris_runtime.schema import ComputeKind

# The canonical device-bridge defaults live on BridgeLimits; Settings derives from them so a
# tuning change happens in exactly one place.
_DEFAULT_BRIDGE_LIMITS = BridgeLimits()

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
    supabase_jwt_secret: str | None = None
    # Base64 AES master key for BYOK at-rest encryption (Phase 2), injected from the secret manager
    # as an env var — never the .env, never the DB. Absent ⇒ BYOK is off (no per-user key storage).
    key_enc_master: str | None = None
    # Keyless ("Draft") build admission control (keyless-fallbacks T6). Draft builds run on a slow,
    # shared local runtime, so the operator can switch the tier off and ration it: a per-tenant
    # per-day cap and a concurrency limit (one in-flight keyless build at a time by default). These
    # govern ONLY keyless builds — a fully-keyed build hits the fast hosted provider, unthrottled.
    draft_tier_enabled: bool = True
    draft_daily_cap: int = 10
    draft_max_concurrent: int = 1
    explain_daily_cap: int = 50
    # Where the keyless local inference runs — CPU (default) or GPU. The image self-selects at boot;
    # this declares it for the Draft UI's compute badge, set per environment to match where the
    # inference app is deployed. Any other env value falls back to CPU.
    keyless_compute: ComputeKind = ComputeKind.CPU
    # Device-bridge bounds (device-compute Draft builds): how long the tab may go silent before
    # its build is failed as disconnected, and the per-completion ceiling for a tab that polls
    # but never answers. Tuned per environment when proxies or device profiles demand it.
    device_bridge_liveness_s: float = _DEFAULT_BRIDGE_LIMITS.liveness_s
    device_bridge_completion_timeout_s: float = _DEFAULT_BRIDGE_LIMITS.completion_timeout_s
    # The explainer-video operator kill-switch (plan §3.0 item 5). Default OFF — fail-closed, so a
    # mid-workstream prod promote can never expose a half-built video surface; dev environments
    # turn it on explicitly (VIDEO_GENERATION_ENABLED=true in .env / per-env CD vars).
    video_generation_enabled: bool = False
    # How often the in-process video worker polls an idle queue (tests turn this way down).
    video_worker_poll_seconds: float = 2.0
    # How many in-process video workers drain the queue concurrently (plan §8.4: 2 local). They
    # share the queue (SKIP-LOCKED claims never double-serve) and the process-wide Claude rate
    # limiter, so more workers overlap renders without bursting the org limit. Cloud scales w/ KEDA.
    video_worker_count: int = 2
    # Lease window (seconds): a job whose worker hasn't heartbeated within it is considered dead and
    # requeued by the sweep (V7-T4). The worker sweep uses it; infra/video.bicep passes it as the
    # env var so the dedicated worker and any operator override agree.
    video_lease_seconds: int = 300
    # Whether THIS process drains the queue in-process (V7). True (default) = the single-process
    # path: `make run` locally runs the worker inside the API. The cloud API sets it False
    # (app.bicep) so it ENQUEUES only and the dedicated worker container renders — otherwise the
    # API's stub-pipeline workers (no Manim in the lean API image) would race the real worker.
    video_inproc_worker_enabled: bool = True
    # The course-cover-image operator kill-switch (course-cover-images). Default OFF — fail-closed,
    # like video: a keyed build only auto-enqueues a cover when this is on, and the worker only ever
    # runs when there are jobs to drain. Turn it on per-env (COVER_GENERATION_ENABLED=true).
    cover_generation_enabled: bool = False
    # How often the in-process cover worker polls an idle queue (tests turn this way down).
    cover_worker_poll_seconds: float = 2.0
    # How many in-process cover workers drain the queue concurrently. They share the queue
    # (SKIP-LOCKED claims never double-serve) and the process-wide Claude rate limiter. Cloud scales
    # the dedicated worker with KEDA (infra/cover.bicep) instead.
    cover_worker_count: int = 2
    # Lease window (seconds): a cover job whose worker hasn't heartbeated within it is considered
    # dead and requeued by the sweep. infra/cover.bicep passes it as the env var so the dedicated
    # worker and any operator override agree.
    cover_lease_seconds: int = 300
    # Whether THIS process drains the cover queue in-process. True (default) = `make run` renders
    # covers inside the API; the cloud API sets it False (app.bicep) so it ENQUEUES only and the
    # dedicated cover-worker container renders.
    cover_inproc_worker_enabled: bool = True
    # Admin allowlist for the signup invite-gate screen: the lowercased emails permitted to manage
    # the shared invite code (LUNARIS_ADMIN_EMAILS, comma-separated). Empty ⇒ no admins, so the
    # admin endpoints 403 everyone — a deploy must set the owner's email to open the screen.
    admin_emails: tuple[str, ...] = ()

    @property
    def has_supabase(self) -> bool:
        """Whether Supabase service-role creds are present (selects the durable run history)."""
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def has_byok(self) -> bool:
        """Whether BYOK is configured — a master key AND Supabase to persist encrypted keys to."""
        return bool(self.key_enc_master and self.has_supabase)

    @property
    def has_embeddings(self) -> bool:
        """Whether the embeddings key is present (the durable corpus needs it to ingest)."""
        return bool(self.embeddings_api_key)

    @property
    def has_auth(self) -> bool:
        """Whether end-user auth is configured (an HS256 secret and/or a JWKS URL → a verifier
        exists). When True, runtime config is per-user (DB); when False, it's the file store
        (single-user dev). Mirrors the verifier composition in ``_build_user_verifier``."""
        return bool(self.supabase_jwt_secret or self.supabase_url)

    def is_admin(self, email: str | None) -> bool:
        """Whether ``email`` is on the signup-gate admin allowlist (case-insensitive). A token with
        no email claim, or an empty allowlist, is never an admin."""
        return bool(email and email.strip().lower() in self.admin_emails)


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
        supabase_jwt_secret=os.getenv("SUPABASE_JWT_SECRET") or None,
        key_enc_master=os.getenv("LUNARIS_KEY_ENC_MASTER") or None,
        draft_tier_enabled=_env_flag("LUNARIS_DRAFT_TIER_ENABLED", default=True),
        draft_daily_cap=_env_int("LUNARIS_DRAFT_DAILY_CAP", default=10),
        draft_max_concurrent=_env_int("LUNARIS_DRAFT_MAX_CONCURRENT", default=1),
        explain_daily_cap=_env_int("LUNARIS_EXPLAIN_DAILY_CAP", default=50),
        keyless_compute=_env_compute("LUNARIS_KEYLESS_COMPUTE", default=ComputeKind.CPU),
        device_bridge_liveness_s=_env_float(
            "LUNARIS_DEVICE_BRIDGE_LIVENESS_S", default=_DEFAULT_BRIDGE_LIMITS.liveness_s
        ),
        device_bridge_completion_timeout_s=_env_float(
            "LUNARIS_DEVICE_BRIDGE_COMPLETION_TIMEOUT_S",
            default=_DEFAULT_BRIDGE_LIMITS.completion_timeout_s,
        ),
        video_generation_enabled=_env_flag("VIDEO_GENERATION_ENABLED", default=False),
        video_worker_poll_seconds=_env_float("LUNARIS_VIDEO_WORKER_POLL_S", default=2.0),
        video_worker_count=_env_int("LUNARIS_VIDEO_WORKER_COUNT", default=2),
        video_lease_seconds=_env_int("LUNARIS_VIDEO_LEASE_SECONDS", default=300),
        video_inproc_worker_enabled=_env_flag("LUNARIS_VIDEO_INPROC_WORKER", default=True),
        cover_generation_enabled=_env_flag("COVER_GENERATION_ENABLED", default=False),
        cover_worker_poll_seconds=_env_float("LUNARIS_COVER_WORKER_POLL_S", default=2.0),
        cover_worker_count=_env_int("LUNARIS_COVER_WORKER_COUNT", default=2),
        cover_lease_seconds=_env_int("LUNARIS_COVER_LEASE_SECONDS", default=300),
        cover_inproc_worker_enabled=_env_flag("LUNARIS_COVER_INPROC_WORKER", default=True),
        admin_emails=_env_csv_lower("LUNARIS_ADMIN_EMAILS"),
    )


def _env_flag(name: str, *, default: bool) -> bool:
    """Read a boolean env var: ``1/true/yes/on`` (any case) is True, ``0/false/no/off`` is False,
    anything else (or unset) falls back to ``default``."""
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, *, default: int) -> int:
    """Read a non-negative integer env var, falling back to ``default`` when unset or malformed."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    # >= 0, deliberately: zero is a valid operator choice ("no Draft builds today"), not malformed.
    return value if value >= 0 else default


def _env_float(name: str, *, default: float) -> float:
    """Read a positive, finite float env var, falling back to ``default`` when unset or malformed —
    a typo'd timeout must degrade to the safe default: never a zero bound that fails every build,
    never an ``inf`` that builds a watchdog which can't fire."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except (ValueError, OverflowError):
        return default
    return value if math.isfinite(value) and value > 0 else default


def _env_csv_lower(name: str) -> tuple[str, ...]:
    """Read a comma-separated env var into a tuple of lowercased, stripped, non-empty values —
    the admin-email allowlist. Lowercasing here makes ``Settings.is_admin`` a plain membership test.
    """
    raw = os.getenv(name) or ""
    return tuple(item.strip().lower() for item in raw.split(",") if item.strip())


def _env_compute(name: str, *, default: ComputeKind) -> ComputeKind:
    """The keyless compute kind ("cpu"/"gpu") from env ``name``; any other value → ``default``."""
    raw = (os.getenv(name) or "").strip().lower()
    return ComputeKind(raw) if raw in (ComputeKind.CPU, ComputeKind.GPU) else default
