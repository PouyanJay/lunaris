from lunaris_live.voice.protocols.provider import IVoiceProvider
from lunaris_live.voice.providers.elevenlabs import ElevenLabsVoiceProvider


def get_voice_provider() -> IVoiceProvider:
    return ElevenLabsVoiceProvider()
