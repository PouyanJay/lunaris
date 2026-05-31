from pathlib import Path
from typing import Annotated

import structlog
from fastapi import Depends
from lunaris_agent import (
    build_agent_course_builder,
    build_orchestrator,
    build_stub_orchestrator,
)
from lunaris_runtime.persistence import (
    CourseStore,
    InMemoryRunStore,
    IRunStore,
    SupabaseRunStore,
)

from .config import Settings, get_settings
from .secrets import AnthropicProbeValidator, ISecretValidator, SecretStore
from .service import CourseService, PipelineFactory

logger = structlog.get_logger()

# LUNARIS_PIPELINE → the per-run pipeline factory. ``agent`` (the default) is the real deep-agent
# harness; ``stub`` is the deterministic no-key demo; ``live`` is the legacy orchestrator.
_PIPELINE_FACTORIES: dict[str, PipelineFactory] = {
    "stub": build_stub_orchestrator,
    "agent": build_agent_course_builder,
    "live": build_orchestrator,
}


# One run store per process, shared across requests (mirrors _secret_stores). The in-memory
# fallback MUST be a singleton or the sidebar would see an empty history every request; the
# Supabase store is shared too, so its lazy client is built once, not per request. Tests inject
# their own via the get_course_service override.
_in_memory_run_store = InMemoryRunStore()
_supabase_run_store = SupabaseRunStore()


def get_run_store(settings: Annotated[Settings, Depends(get_settings)]) -> IRunStore:
    """The run-history index: Supabase when creds are present, else the in-process fallback.

    The Supabase client is lazy, so the process-wide instance needs no network until the first
    write touches the environment. Without creds, history lives for the process lifetime only
    (durable, cross-machine history requires Supabase).
    """
    if settings.has_supabase:
        return _supabase_run_store
    return _in_memory_run_store


def get_course_service(
    settings: Annotated[Settings, Depends(get_settings)],
    run_store: Annotated[IRunStore, Depends(get_run_store)],
) -> CourseService:
    """Compose the CourseService for the configured pipeline (overridable in tests)."""
    store = CourseStore(settings.course_dir)
    factory = _PIPELINE_FACTORIES.get(settings.pipeline)
    if factory is None:
        # An unrecognized LUNARIS_PIPELINE shouldn't silently run the paid live path; warn loudly.
        logger.warning("unknown_pipeline_falling_back", requested=settings.pipeline, default="live")
        factory = build_orchestrator
    return CourseService(store, factory, run_store)


CourseServiceDep = Annotated[CourseService, Depends(get_course_service)]

# One SecretStore per secrets-file path (it owns process env + the on-disk file), so all
# requests share the same in-memory + on-disk state. Tests override get_secret_store.
_secret_stores: dict[Path, SecretStore] = {}


def get_secret_store(settings: Annotated[Settings, Depends(get_settings)]) -> SecretStore:
    """The process-wide secret store for the configured secrets path."""
    path = settings.secrets_path
    if path not in _secret_stores:
        _secret_stores[path] = SecretStore(path)
    return _secret_stores[path]


def get_secret_validator() -> ISecretValidator:
    """The live secret validator (probes Anthropic). Tests override with an accepting one."""
    return AnthropicProbeValidator()


SecretStoreDep = Annotated[SecretStore, Depends(get_secret_store)]
SecretValidatorDep = Annotated[ISecretValidator, Depends(get_secret_validator)]
