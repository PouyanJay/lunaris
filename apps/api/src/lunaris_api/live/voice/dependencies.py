from typing import Annotated

from fastapi import Depends, HTTPException
from lunaris_live.voice.durable_service import DurableVoiceService
from lunaris_live.voice.models.dependencies import VoiceDependencies
from lunaris_live.voice.protocols.provider import IVoiceProvider
from lunaris_live.voice.protocols.service import IVoiceService

from ...config import Settings, get_settings
from ...dependencies import CostEventStoreDep, OptionalUserIdDep, SubjectCostStoreDep
from ..corpus.dependencies import get_corpus_access_guard
from ..corpus.protocols.access_guard import ICorpusAccessGuard
from ..dependencies import get_live_credential_resolver, resolve_graph_store
from ..session.dependencies import _resolve_session_store
from .metered_provider import MeteredVoiceProvider
from .metering_context import VoiceMeteringContext
from .metering_dependencies import VoiceMeteringDependencies
from .provider_dependencies import get_voice_provider
from .session_reader import StoredVoiceSessions
from .storage_dependencies import resolve_voice_storage


async def get_live_voice_service(
    session_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    owner_id: OptionalUserIdDep,
    events: CostEventStoreDep,
    costs: SubjectCostStoreDep,
    provider: Annotated[IVoiceProvider, Depends(get_voice_provider)],
    source_access: Annotated[ICorpusAccessGuard | None, Depends(get_corpus_access_guard)] = None,
) -> IVoiceService:
    if not settings.live_voice_enabled:
        raise HTTPException(503, "Voice is unavailable. Continue with text.")
    if settings.has_supabase and owner_id is None:
        raise HTTPException(401, "Sign in to use voice.")
    storage = resolve_voice_storage(settings)
    metered = MeteredVoiceProvider(
        provider,
        VoiceMeteringContext(session_id, owner_id, settings.live_session_budget_usd),
        VoiceMeteringDependencies(get_live_credential_resolver(settings), events, costs),
    )
    return DurableVoiceService(
        VoiceDependencies(
            ledger=storage.ledger,
            audio=storage.audio,
            provider=metered,
            sessions=StoredVoiceSessions(
                _resolve_session_store(settings),
                graphs=resolve_graph_store(settings),
                source_access=source_access,
            ),
        )
    )
