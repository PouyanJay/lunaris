import os
from pathlib import Path
from typing import Annotated, get_type_hints

import structlog
from fastapi import Depends
from lunaris_agent import (
    LessonRegenerator,
    build_agent_course_builder,
    build_orchestrator,
    build_stub_orchestrator,
)
from lunaris_runtime.persistence import (
    CourseStore,
    InMemoryRunEventStore,
    InMemoryRunStore,
    IRunEventStore,
    IRunStore,
    SupabaseRunStore,
)

from .config import Settings, get_settings
from .explain import ClaudeExplainer, IExplainer
from .run_registry import RunRegistry
from .secrets import KNOWN_SECRETS, AnthropicProbeValidator, ISecretValidator, SecretStore
from .service import CourseService, PipelineFactory

logger = structlog.get_logger()

# Worker-tier model for the (cheap, short) Explain calls; overridable via the usual env knob.
_EXPLAIN_MODEL = "claude-haiku-4-5-20251001"

# LUNARIS_PIPELINE → the per-run pipeline factory. ``agent`` (the default) is the real deep-agent
# harness; ``stub`` is the deterministic no-key demo; ``live`` is the legacy orchestrator.
_PIPELINE_FACTORIES: dict[str, PipelineFactory] = {
    "stub": build_stub_orchestrator,
    "agent": build_agent_course_builder,
    "live": build_orchestrator,
}


def pipeline_supports_lesson_regeneration(pipeline: str) -> bool:
    """Whether the configured pipeline implements the optional ``LessonRegenerator`` capability.

    Derived from the factory's declared return type — never by instantiating it (building the agent
    pipeline constructs LLM clients and needs an API key) — so it stays in lockstep with the
    ``isinstance(pipeline, LessonRegenerator)`` gate in ``CourseService.regenerate_lesson``: the
    single-shot Orchestrator regenerates, the deep-agent builder does not. The web reads this to
    show or hide the per-lesson regenerate action instead of offering a button that always 501s.
    (``issubclass`` against the runtime_checkable Protocol matches method *names* only — sufficient
    for the closed, hand-curated set of pipeline factories.)
    """
    factory = _PIPELINE_FACTORIES.get(pipeline)
    if factory is None:
        return False
    try:
        return_type = get_type_hints(factory).get("return")
    except Exception:
        # A factory whose annotations can't be resolved (e.g. PEP 563 string hints losing a name in
        # scope) falls back to "unsupported" — the same fail-safe as an unknown pipeline above.
        return False
    return isinstance(return_type, type) and issubclass(return_type, LessonRegenerator)


# One run store per process, shared across requests (mirrors _secret_stores). The in-memory
# fallback MUST be a singleton or the sidebar would see an empty history every request; the
# Supabase store is shared too, so its lazy client is built once, not per request. Tests inject
# their own via the get_course_service override.
_in_memory_run_store = InMemoryRunStore()
_supabase_run_store = SupabaseRunStore()

# The replayable build-event log (build-timeline Phase B), one per process (same singleton rationale
# as the run store: an in-memory log must be shared so a build's writes survive for a later replay
# read). Phase B/T0 ships the in-memory store only; the Supabase-backed log lands in T1.
_in_memory_run_event_store = InMemoryRunEventStore()

# One in-flight run-task registry per process, shared across requests — the cancel request and the
# build request must see the same in-flight set, so this MUST be a singleton.
_run_registry = RunRegistry()


def get_run_registry() -> RunRegistry:
    """The process-wide registry of in-flight build tasks (for cancellation)."""
    return _run_registry


def get_run_store(settings: Annotated[Settings, Depends(get_settings)]) -> IRunStore:
    """The run-history index: Supabase when creds are present, else the in-process fallback.

    The Supabase client is lazy, so the process-wide instance needs no network until the first
    write touches the environment. Without creds, history lives for the process lifetime only
    (durable, cross-machine history requires Supabase).
    """
    if settings.has_supabase:
        return _supabase_run_store
    return _in_memory_run_store


def get_run_event_store() -> IRunEventStore:
    """The replayable build-event log. Phase B/T0 wires the in-process store unconditionally; T1
    swaps in the Supabase-backed log when creds are present (mirroring ``get_run_store``)."""
    return _in_memory_run_event_store


def get_course_service(
    settings: Annotated[Settings, Depends(get_settings)],
    run_store: Annotated[IRunStore, Depends(get_run_store)],
    registry: Annotated[RunRegistry, Depends(get_run_registry)],
    event_store: Annotated[IRunEventStore, Depends(get_run_event_store)],
) -> CourseService:
    """Compose the CourseService for the configured pipeline (overridable in tests)."""
    store = CourseStore(settings.course_dir)
    factory = _PIPELINE_FACTORIES.get(settings.pipeline)
    if factory is None:
        # An unrecognized LUNARIS_PIPELINE shouldn't silently run the paid live path; warn loudly.
        logger.warning("unknown_pipeline_falling_back", requested=settings.pipeline, default="live")
        factory = build_orchestrator
    return CourseService(store, factory, run_store, registry, event_store)


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


def explain_is_available() -> bool:
    """Whether plain-language Explain can run — i.e. an Anthropic key is reachable.

    Keyed on the environment variable (the unified runtime source, named once in ``KNOWN_SECRETS``):
    a key set in ``.env`` OR entered via the Settings UI (the SecretStore applies stored keys to
    ``os.environ``) both satisfy it.
    """
    return bool(os.getenv(KNOWN_SECRETS["anthropic"]))


# One explainer per process (built lazily on first availability). NOT cached as None — the key can
# be added at runtime via the Settings UI, so availability is re-checked every call.
_explainer: ClaudeExplainer | None = None


def get_explainer() -> IExplainer | None:
    """The transcript-blob explainer (worker tier), or None when no Anthropic key is reachable.

    None makes the route fail closed with a 503 instead of constructing a client that can't call
    out; the web mirrors this via ``supportsExplain`` so it never shows a button that would 503.
    """
    global _explainer
    if not explain_is_available():
        return None
    if _explainer is None:
        _explainer = ClaudeExplainer(os.getenv("LUNARIS_MODEL_WORKER", _EXPLAIN_MODEL))
    return _explainer


ExplainerDep = Annotated[IExplainer | None, Depends(get_explainer)]
