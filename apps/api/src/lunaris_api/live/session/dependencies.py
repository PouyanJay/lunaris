from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from lunaris_live.session import (
    ClaudeGrader,
    ClaudeTutor,
    IGrader,
    IInterviewer,
    IKnowledgeStore,
    ISessionStore,
    ISimRegistry,
    ITutor,
    MemoryKnowledgeStore,
    MemorySessionStore,
    StubGrader,
    StubInterviewer,
    StubSimRegistry,
    StubTutor,
    SupabaseKnowledgeStore,
    SupabaseSessionStore,
)

from ...config import Settings, get_settings
from ...dependencies import CostEventStoreDep, SubjectCostStoreDep
from ..dependencies import (
    get_live_credential_resolver,
    get_live_graph_service,
    resolve_graph_store,
    resolve_strong_model,
    resolve_worker_model,
)
from ..service import LiveGraphService
from .service import LiveSessionService
from .throttle import LiveSessionThrottle

# One durable store per process — same lazy-client rationale as the graph store: the service-role
# client is built on first write, so the singleton needs no creds and no network until then.
_supabase_session_store = SupabaseSessionStore()
_supabase_knowledge_store = SupabaseKnowledgeStore()

# The in-memory fallbacks MUST be singletons: opening a session and the next turn of it are
# separate requests, so a per-request store would lose the session — and the learner's beliefs —
# between them.
_memory_session_store = MemorySessionStore()
_memory_knowledge_store = MemoryKnowledgeStore()


def _resolve_session_store(settings: Settings) -> ISessionStore:
    """Durable where Supabase is configured, in-process otherwise (offline dev and the suite)."""
    return _supabase_session_store if settings.has_supabase else _memory_session_store


def _resolve_knowledge_store(settings: Settings) -> IKnowledgeStore:
    """Durable where Supabase is configured, in-process otherwise (offline dev and the suite)."""
    return _supabase_knowledge_store if settings.has_supabase else _memory_knowledge_store


def get_live_tutor(settings: Annotated[Settings, Depends(get_settings)]) -> ITutor:
    """The model-backed tutor, or the deterministic one under ``LUNARIS_PIPELINE=stub``.

    A dependency in its own right rather than something the service composes privately, because it
    is the collaborator most worth substituting: the failure that matters most here is a tutor that
    cannot speak, and a test can only stage that by putting a silent one in its place.

    Teaching runs on the strong tier (A1) — the same tier the map was compiled on. It is the
    quality surface of the whole product, and a session taught by a cheaper model than the map it
    walks would be a difference no one chose.
    """
    return StubTutor() if settings.pipeline == "stub" else ClaudeTutor(resolve_strong_model())


def get_live_sims(settings: Annotated[Settings, Depends(get_settings)]) -> ISimRegistry | None:
    """Which Tier 3 simulators this deployment can mount, or ``None`` for none (P2b T6).

    **Off unless asked for**, and that is the honest default rather than a timid one. The only
    registry that exists today is the stub, which mounts a placeholder that proves the socket and
    teaches nothing — and its report becomes evidence through the ordinary answer path, so leaving
    it on would grade learners on a placeholder. With no registry, a concept whose every criterion
    needs a simulator keeps P2a's position: taught here, not checkable here.

    A dependency of its own, like the tutor and grader, because it is the collaborator a test wants
    to substitute: what Phase 3 changes is which sims exist, and every seam above this one should
    not notice.
    """
    return StubSimRegistry() if settings.live_sims == "stub" else None


def get_live_interviewer(settings: Annotated[Settings, Depends(get_settings)]) -> IInterviewer:
    """The interviewer that opens a session on a topic (P2c T1): the deterministic one under
    ``LUNARIS_PIPELINE=stub``, and — until T2 lands the model-backed one — the same one everywhere,
    so the walking skeleton crosses every layer with the plainest voice it can.

    A dependency of its own for the reason the tutor is: it is the collaborator a test wants to
    substitute, and the failure worth staging is an interviewer with nothing to ask.
    """
    # T2 keys this on ``settings.pipeline`` the way the tutor and grader are.
    del settings
    return StubInterviewer()


def get_live_grader(settings: Annotated[Settings, Depends(get_settings)]) -> IGrader:
    """The model-backed grader, or the deterministic one under ``LUNARIS_PIPELINE=stub``.

    A dependency of its own for the same reason the tutor is: a grader that cannot answer is the
    failure worth staging in a test, and an answer wrongly scored is the mistake that compounds —
    every verdict it gets wrong is written into a belief the director acts on for the rest of the
    session.

    Runs on the worker tier (A1): teaching is the quality surface, judging one answer against one
    explicit do-statement is a classification.
    """
    return StubGrader() if settings.pipeline == "stub" else ClaudeGrader(resolve_worker_model())


@lru_cache
def _get_live_session_throttle(settings: Settings) -> LiveSessionThrottle:
    """The process-wide session throttle for these settings.

    Cached on the frozen ``Settings`` value because the per-day counts have to be shared across
    requests: the service is built per request, and a per-request throttle would never see the
    openings it is supposed to be counting. Keyed on the whole ``Settings`` (not just the Live
    fields) so it cannot drift as the config surface grows; tests reset it via
    ``_get_live_session_throttle.cache_clear()``.
    """
    return LiveSessionThrottle(open_daily_cap=settings.live_session_daily_cap)


def get_live_session_service(
    settings: Annotated[Settings, Depends(get_settings)],
    tutor: Annotated[ITutor, Depends(get_live_tutor)],
    grader: Annotated[IGrader, Depends(get_live_grader)],
    sims: Annotated[ISimRegistry | None, Depends(get_live_sims)],
    interviewer: Annotated[IInterviewer, Depends(get_live_interviewer)],
    compiles: Annotated[LiveGraphService, Depends(get_live_graph_service)],
    cost_event_store: CostEventStoreDep,
    subject_cost_store: SubjectCostStoreDep,
) -> LiveSessionService:
    """Live's session plane as a request dependency.

    Takes the *same* graph store the compile plane writes to rather than composing a second one —
    a session that read from a different store than the compiler wrote to would find no maps at all,
    and it would look like a data problem rather than the wiring one it is. And takes the compile
    plane itself (P2c), the very service the graph routes use, so a session opened on a topic is
    admitted by the same throttle and lands in the same store as a map compiled by hand.
    """
    return LiveSessionService(
        resolve_graph_store(settings),
        _resolve_session_store(settings),
        knowledge=_resolve_knowledge_store(settings),
        tutor=tutor,
        grader=grader,
        session_budget_s=settings.live_session_budget_s,
        # The ledger and the tenant's keys come from Studio's composition root: Live is a second
        # product, not a second platform, so a tenant's spend and a tenant's key are the same ones
        # either way. What differs is only the subject a cost is filed under (``LIVE_SESSION``).
        cost_event_store=cost_event_store,
        subject_cost_store=subject_cost_store,
        credential_resolver=get_live_credential_resolver(settings),
        throttle=_get_live_session_throttle(settings),
        session_budget_usd=settings.live_session_budget_usd,
        sims=sims,
        compiles=compiles,
        interviewer=interviewer,
    )


LiveSessionServiceDep = Annotated[LiveSessionService, Depends(get_live_session_service)]
