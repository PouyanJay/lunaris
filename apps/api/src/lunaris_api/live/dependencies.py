from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from lunaris_live.graph import (
    ClaudeGraphCompiler,
    IGraphCompiler,
    IGraphStore,
    MemoryGraphStore,
    StubGraphCompiler,
    SupabaseGraphStore,
)
from lunaris_runtime.credentials import CredentialResolver
from lunaris_runtime.run_config import resolve_config

from ..config import Settings, get_settings
from ..dependencies import (
    CostEventStoreDep,
    SubjectCostStoreDep,
    get_video_credential_resolver,
)
from .graph_throttle import LiveGraphThrottle
from .launched_compiles import LaunchedCompiles
from .service import LiveGraphService

#: Decomposition decides what the course is made of and every later phase reads it, so it runs on
#: the strong tier, not the bulk one. Same env knob Studio's tiers use, so a tenant's model choice
#: covers both products. (Splitting decomposition from spec authoring across two tiers is a
#: latency/cost lever; one tier keeps this honest until there is a measurement to tune to.)
_DEFAULT_MODEL = "claude-opus-4-8"


def resolve_strong_model() -> str:
    """The model Live's quality surfaces run on — the compiler's decomposition and the tutor.

    One function rather than a constant per composition root, so a tenant's model choice cannot end
    up meaning two different things inside one product: a session taught by a weaker model than the
    map it walks would be a difference nobody configured.
    """
    return resolve_config("LUNARIS_MODEL_STRONG") or _DEFAULT_MODEL


#: Grading one answer against one explicit do-statement is a classification, not a quality surface,
#: so it runs on the bulk tier — the same knob Studio's workers read.
_DEFAULT_WORKER_MODEL = "claude-haiku-4-5-20251001"


def resolve_worker_model() -> str:
    """The model Live's classification surfaces run on (A1)."""
    return resolve_config("LUNARIS_MODEL_WORKER") or _DEFAULT_WORKER_MODEL


# One durable store per process, same lazy-client rationale as Studio's stores: the service-role
# client is built on first write, so the singleton needs no creds and no network until then.
_supabase_graph_store = SupabaseGraphStore()

# The in-memory fallback MUST be a singleton — a compile and the later read of that graph are
# separate requests, so a per-request store would lose the graph between them.
_memory_graph_store = MemoryGraphStore()


def resolve_graph_store(settings: Settings) -> IGraphStore:
    """Durable where Supabase is configured, in-process otherwise (offline dev and the suite).

    Public because the session plane composes against the *same* store: a session reading from a
    different store than the compiler wrote to would find no maps, and it would read as a data
    problem rather than the wiring one it is.
    """
    return _supabase_graph_store if settings.has_supabase else _memory_graph_store


def _resolve_compiler(settings: Settings) -> IGraphCompiler:
    """The model-backed compiler, or the deterministic stub under ``LUNARIS_PIPELINE=stub``.

    Keyed to the same switch Studio's pipeline reads, so one setting decides whether the whole
    process talks to a provider — which is what makes the test suite and offline dev hermetic
    without either product needing its own opt-out.
    """
    if settings.pipeline == "stub":
        return StubGraphCompiler()
    return ClaudeGraphCompiler(resolve_strong_model(), deadline_s=settings.live_compile_deadline_s)


@lru_cache
def _get_live_graph_throttle(settings: Settings) -> LiveGraphThrottle:
    """The process-wide Live throttle for the given settings (T8c).

    Cached on the frozen ``Settings`` value because the in-flight slots and per-day counts have to
    be shared across requests: ``get_live_graph_service`` builds a service per request, and a
    per-request throttle would never see the compile it is supposed to be counting. Keyed on the
    whole ``Settings`` (not just the Live fields) so it cannot drift as the config surface grows;
    tests reset it via ``_get_live_graph_throttle.cache_clear()`` (see the API conftest).
    """
    return LiveGraphThrottle(
        compile_daily_cap=settings.live_compile_daily_cap,
        compile_max_concurrent=settings.live_compile_max_concurrent,
        extend_daily_cap=settings.live_extend_daily_cap,
    )


# One registry per process, for the reason the throttle is cached: the compile plane is built per
# request, and a session asking how its compile ended is a later request than the one that launched
# it. Holds task handles, not settings, so it is not keyed on them.
_launched_compiles = LaunchedCompiles()


def launched_compiles() -> LaunchedCompiles:
    """The process-wide registry of launched compiles (one per process, like the throttle)."""
    return _launched_compiles


def get_live_credential_resolver(settings: Settings) -> CredentialResolver | None:
    """The BYOK resolver a Live compile runs on, or ``None`` when BYOK is off.

    Delegates to the shared vault-backed resolver rather than composing a second one — the same
    alias the cover worker takes, for the same reason: one tenant, one set of keys, however many
    surfaces spend them. ``None`` (no master key — local dev / single-user) leaves the compiler
    reading the process environment, unchanged.
    """
    return get_video_credential_resolver(settings)


def get_live_graph_service(
    settings: Annotated[Settings, Depends(get_settings)],
    cost_event_store: CostEventStoreDep,
    subject_cost_store: SubjectCostStoreDep,
) -> LiveGraphService:
    """Live's compile plane as a request dependency.

    The cost stores and the BYOK resolver come from Studio's composition root: Live is a second
    product, not a second platform, so a tenant's key and a tenant's ledger are the same ones either
    way — what differs is only the subject a cost is filed under (``LIVE_GRAPH``, chosen in the
    service). Reusing the shared getters is also what keeps the two products' spend in one place,
    which is the entire reason D2 generalized the ledger's key rather than giving Live its own.
    """
    return LiveGraphService(
        _resolve_compiler(settings),
        resolve_graph_store(settings),
        cost_event_store=cost_event_store,
        subject_cost_store=subject_cost_store,
        credential_resolver=get_live_credential_resolver(settings),
        throttle=_get_live_graph_throttle(settings),
        graph_budget_usd=settings.live_graph_budget_usd,
        launched=_launched_compiles,
    )


LiveGraphServiceDep = Annotated[LiveGraphService, Depends(get_live_graph_service)]
