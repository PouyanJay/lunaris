from typing import Annotated

from fastapi import Depends
from lunaris_live.graph import (
    IGraphStore,
    MemoryGraphStore,
    StubGraphCompiler,
    SupabaseGraphStore,
)

from ..config import Settings, get_settings
from .service import LiveGraphService

# One durable store per process, same lazy-client rationale as Studio's stores: the service-role
# client is built on first write, so the singleton needs no creds and no network until then.
_supabase_graph_store = SupabaseGraphStore()

# The in-memory fallback MUST be a singleton — a compile and the later read of that graph are
# separate requests, so a per-request store would lose the graph between them.
_memory_graph_store = MemoryGraphStore()


def _resolve_graph_store(settings: Settings) -> IGraphStore:
    """Durable where Supabase is configured, in-process otherwise (offline dev and the suite)."""
    return _supabase_graph_store if settings.has_supabase else _memory_graph_store


def get_live_graph_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LiveGraphService:
    """Live's compile plane as a request dependency.

    The compiler is the deterministic stub until T3 lands the model-backed one; both satisfy
    ``IGraphCompiler``, so this is the only line that changes when it does.
    """
    return LiveGraphService(StubGraphCompiler(), _resolve_graph_store(settings))


LiveGraphServiceDep = Annotated[LiveGraphService, Depends(get_live_graph_service)]
