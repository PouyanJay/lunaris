"""Product session UI with authenticated simulator state and durable fixture voice transport."""

from collections.abc import AsyncIterator

from approved_sim_app import app, sessions
from lunaris_api.live.voice.dependencies import get_live_voice_service
from lunaris_api.live.voice.session_reader import StoredVoiceSessions
from lunaris_live.voice.durable_service import DurableVoiceService
from lunaris_live.voice.models.dependencies import VoiceDependencies
from lunaris_live.voice.models.policy import VoicePolicy
from lunaris_live.voice.models.recorded_audio import RecordedAudio
from lunaris_live.voice.models.transcription import Transcription
from lunaris_live.voice.persistence.memory_audio_store import MemoryVoiceAudioStore
from lunaris_live.voice.persistence.memory_ledger import MemoryVoiceLedger


class _Provider:
    def __init__(self):
        self.transcriptions = []
        self.speech = []

    async def transcribe(self, audio: RecordedAudio, *, run_id: str) -> Transcription:
        assert 0 < audio.duration_s <= 60
        self.transcriptions.append(run_id)
        return Transcription("A fraction is a part of a whole.", "browser-fixture", "fixture-v1")

    async def speak(self, text: str, *, run_id: str) -> AsyncIterator[bytes]:
        self.speech.append({"text": text, "run_id": run_id})
        for _ in range(4):
            yield b"\x01\x00" * 1200


provider = _Provider()
voice = DurableVoiceService(
    VoiceDependencies(
        ledger=MemoryVoiceLedger(sessions),
        audio=MemoryVoiceAudioStore(),
        provider=provider,
        sessions=StoredVoiceSessions(sessions),
    ),
    policy=VoicePolicy(speech_provider="browser-fixture", speech_model="fixture-v1"),
)
app.dependency_overrides[get_live_voice_service] = lambda: voice


@app.get("/test/voice-calls")
async def voice_calls():
    return {"transcriptions": provider.transcriptions, "speech": provider.speech}
