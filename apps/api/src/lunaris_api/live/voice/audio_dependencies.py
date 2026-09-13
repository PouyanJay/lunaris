from functools import lru_cache

from lunaris_live.voice.persistence.memory_audio_store import MemoryVoiceAudioStore
from lunaris_live.voice.persistence.supabase_audio_store import SupabaseVoiceAudioStore
from lunaris_live.voice.protocols.audio_store import IVoiceAudioStore

from ...config import Settings


@lru_cache
def resolve_voice_audio(settings: Settings) -> IVoiceAudioStore:
    """Retention depends only on storage, including when voice admission is disabled."""
    if settings.has_supabase:
        return SupabaseVoiceAudioStore(
            url=settings.supabase_url, key=settings.supabase_service_role_key
        )
    return MemoryVoiceAudioStore()
