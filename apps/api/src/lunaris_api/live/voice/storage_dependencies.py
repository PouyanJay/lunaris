from dataclasses import dataclass
from functools import lru_cache

from lunaris_live.session import MemorySessionStore
from lunaris_live.voice.persistence.memory_ledger import MemoryVoiceLedger
from lunaris_live.voice.persistence.models.limits import VoiceLimits
from lunaris_live.voice.persistence.supabase_ledger import SupabaseVoiceLedger
from lunaris_live.voice.protocols.audio_store import IVoiceAudioStore
from lunaris_live.voice.protocols.ledger import IVoiceLedger

from ...config import Settings
from ..session.dependencies import _resolve_session_store
from .audio_dependencies import resolve_voice_audio


@dataclass(frozen=True)
class _VoiceStorage:
    ledger: IVoiceLedger
    audio: IVoiceAudioStore


@lru_cache
def resolve_voice_storage(settings: Settings) -> _VoiceStorage:
    """Called synchronously on the API event loop, sharing receipts across request services."""
    # Voice admission is capped at one hour independently of longer text sessions.
    limits = VoiceLimits(session_seconds=min(3600, max(1, int(settings.live_session_budget_s))))
    if settings.has_supabase:
        return _VoiceStorage(
            SupabaseVoiceLedger(limits=limits),
            resolve_voice_audio(settings),
        )
    sessions = _resolve_session_store(settings)
    assert isinstance(sessions, MemorySessionStore)
    return _VoiceStorage(MemoryVoiceLedger(sessions, limits=limits), resolve_voice_audio(settings))
