from lunaris_live.voice.persistence.audio_cleanup import VoiceAudioCleanup

from ...config import Settings
from .audio_dependencies import resolve_voice_audio
from .maintenance import run_voice_cleanup


async def run_voice_retention(settings: Settings) -> None:
    """Keep Live package composition within its API region."""
    await run_voice_cleanup(VoiceAudioCleanup(resolve_voice_audio(settings)))
