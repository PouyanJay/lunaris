from typing import Annotated

from fastapi import Depends
from lunaris_live.session import ISessionStore, MemorySessionStore, SupabaseSessionStore

from ...config import Settings, get_settings
from ..dependencies import resolve_graph_store
from .service import LiveSessionService

# One durable store per process — same lazy-client rationale as the graph store: the service-role
# client is built on first write, so the singleton needs no creds and no network until then.
_supabase_session_store = SupabaseSessionStore()

# The in-memory fallback MUST be a singleton: opening a session and the next turn of it are separate
# requests, so a per-request store would lose the session between them.
_memory_session_store = MemorySessionStore()


def _resolve_session_store(settings: Settings) -> ISessionStore:
    """Durable where Supabase is configured, in-process otherwise (offline dev and the suite)."""
    return _supabase_session_store if settings.has_supabase else _memory_session_store


def get_live_session_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LiveSessionService:
    """Live's session plane as a request dependency.

    Takes the *same* graph store the compile plane writes to rather than composing a second one —
    a session that read from a different store than the compiler wrote to would find no maps at all,
    and it would look like a data problem rather than a wiring one.
    """
    return LiveSessionService(resolve_graph_store(settings), _resolve_session_store(settings))


LiveSessionServiceDep = Annotated[LiveSessionService, Depends(get_live_session_service)]
