"""Local-only capped real-provider fixture; never deploy this app."""

import io
import os
import wave
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

import anyio
import httpx
from approved_sim_app import app, sessions
from lunaris_api.live.voice.dependencies import get_live_voice_service
from lunaris_api.live.voice.session_reader import StoredVoiceSessions
from lunaris_live.voice.durable_service import DurableVoiceService
from lunaris_live.voice.error import VoiceError
from lunaris_live.voice.models.dependencies import VoiceDependencies
from lunaris_live.voice.models.recorded_audio import RecordedAudio
from lunaris_live.voice.models.transcription import Transcription
from lunaris_live.voice.persistence.memory_audio_store import MemoryVoiceAudioStore
from lunaris_live.voice.persistence.memory_ledger import MemoryVoiceLedger
from lunaris_live.voice.providers.elevenlabs import ElevenLabsVoiceProvider
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.metering.cost_scope import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostSubjectType

_SYNTHETIC_TEXT = "HIPAA protects patient privacy. An EHR is an electronic health record."


def _offline_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\1\0" * 16000)
    return output.getvalue()


def _offline_response(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/speech-to-text"):
        return httpx.Response(200, json={"text": _SYNTHETIC_TEXT})
    return httpx.Response(200, content=b"\1\0" * 2400, headers={"content-type": "audio/pcm"})


class _CappedProvider:
    def __init__(self) -> None:
        self.offline = os.getenv("LUNARIS_VOICE_BROWSER_OFFLINE") == "1"
        if not self.offline and os.getenv("LUNARIS_RUN_VOICE_BROWSER_EVAL") != "1":
            raise RuntimeError("Explicit provider browser evaluation opt-in is required")
        self.key = "offline" if self.offline else os.environ["ELEVENLABS_API_KEY"]
        self.started = {"tts": 0, "stt": 0}
        self.metrics: list[dict[str, Any]] = []

    def _admit(self, kind: str) -> None:
        if self.started[kind] >= {"tts": 3, "stt": 2}[kind]:
            raise VoiceError("Evaluation provider call cap reached", status_code=429)
        self.started[kind] += 1

    def _scope(self, run_id: str) -> CostScope:
        return CostScope(
            run_id=run_id,
            subject_type=CostSubjectType.LIVE_SESSION,
            subject_id="synthetic-browser-eval",
            price_book=PriceBook.current(),
        )

    async def transcribe(self, audio: RecordedAudio, *, run_id: str) -> Transcription:
        self._admit("stt")
        scope = self._scope(run_id)
        started = perf_counter()
        metric = {"kind": "stt", "run_id": run_id, "audio_seconds": audio.duration_s}
        self.metrics.append(metric)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_offline_response) if self.offline else None
        ) as client:
            with run_credentials({"ELEVENLABS_API_KEY": self.key}), cost_scope(scope):
                try:
                    result = await ElevenLabsVoiceProvider(client=client).transcribe(
                        audio, run_id=run_id
                    )
                    metric.update(provider=result.provider, model=result.model, status="completed")
                    return result
                finally:
                    metric.update(
                        latency_ms=(perf_counter() - started) * 1000,
                        usage=[asdict(entry) for entry in scope.entries],
                    )

    async def speak(self, text: str, *, run_id: str) -> AsyncIterator[bytes]:
        self._admit("tts")
        scope = self._scope(run_id)
        started, received = perf_counter(), 0
        metric = {"kind": "tts", "run_id": run_id, "canonical_chars": len(text)}
        self.metrics.append(metric)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_offline_response) if self.offline else None
        ) as client:
            with run_credentials({"ELEVENLABS_API_KEY": self.key}), cost_scope(scope):
                stream = ElevenLabsVoiceProvider(client=client).speak(text, run_id=run_id)
                try:
                    async for chunk in stream:
                        if chunk and received == 0:
                            metric["first_pcm_ms"] = (perf_counter() - started) * 1000
                        received += len(chunk)
                        yield chunk
                    metric["status"] = "completed"
                finally:
                    try:
                        with anyio.fail_after(2, shield=True):
                            await stream.aclose()
                    finally:
                        metric.update(
                            audio_seconds=received / 48000,
                            usage=[asdict(entry) for entry in scope.entries],
                        )


provider = _CappedProvider()
if not provider.offline:
    output = Path(os.environ["LUNARIS_VOICE_BROWSER_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / "provider-attempt.claim").open("x") as claim:
        claim.write("At most 3 TTS + 2 STT; never restart this paid attempt automatically.\n")
voice = DurableVoiceService(
    VoiceDependencies(
        ledger=MemoryVoiceLedger(sessions),
        audio=MemoryVoiceAudioStore(),
        provider=provider,
        sessions=StoredVoiceSessions(sessions),
    )
)
app.dependency_overrides[get_live_voice_service] = lambda: voice


@app.get("/test/voice-eval")
async def voice_evidence() -> dict[str, Any]:
    return {
        "offline": provider.offline,
        "calls_started": provider.started,
        "metrics": provider.metrics,
        "billed_cost_usd": None,
        "physical_microphone_tested": False,
        "human_listening_rating": None,
    }
