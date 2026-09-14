from collections.abc import AsyncIterator
from typing import Protocol

from ..models.recorded_audio import RecordedAudio
from ..models.transcription import Transcription


class IVoiceProvider(Protocol):
    async def transcribe(self, audio: RecordedAudio, *, run_id: str) -> Transcription: ...

    def speak(self, text: str, *, run_id: str) -> AsyncIterator[bytes]:
        """Yield mono little-endian signed PCM16 at 24kHz; no container header."""
        ...
