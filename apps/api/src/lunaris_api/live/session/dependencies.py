from typing import Annotated

from fastapi import Depends
from lunaris_live.session import (
    ClaudeGrader,
    ClaudeTutor,
    IGrader,
    IKnowledgeStore,
    ISessionStore,
    ITutor,
    MemoryKnowledgeStore,
    MemorySessionStore,
    StubGrader,
    StubTutor,
    SupabaseKnowledgeStore,
    SupabaseSessionStore,
)

from ...config import Settings, get_settings
from ..dependencies import resolve_graph_store, resolve_strong_model, resolve_worker_model
from .service import LiveSessionService

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


def get_live_session_service(
    settings: Annotated[Settings, Depends(get_settings)],
    tutor: Annotated[ITutor, Depends(get_live_tutor)],
    grader: Annotated[IGrader, Depends(get_live_grader)],
) -> LiveSessionService:
    """Live's session plane as a request dependency.

    Takes the *same* graph store the compile plane writes to rather than composing a second one —
    a session that read from a different store than the compiler wrote to would find no maps at all,
    and it would look like a data problem rather than the wiring one it is.
    """
    return LiveSessionService(
        resolve_graph_store(settings),
        _resolve_session_store(settings),
        knowledge=_resolve_knowledge_store(settings),
        tutor=tutor,
        grader=grader,
        session_budget_s=settings.live_session_budget_s,
    )


LiveSessionServiceDep = Annotated[LiveSessionService, Depends(get_live_session_service)]
