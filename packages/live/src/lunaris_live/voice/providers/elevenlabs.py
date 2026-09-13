import asyncio
import json
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import structlog
from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.metering import record_cost
from lunaris_runtime.metering.rate_policy import RatePolicy
from lunaris_runtime.schema import CostProvider, CostUnit

from ..error import VoiceError
from ..models.recorded_audio import RecordedAudio
from ..models.transcription import Transcription
from ..read_audio import read_audio
from .pronunciation import spoken_text

_logger = structlog.get_logger(__name__)
_BASE = "https://api.elevenlabs.io/v1"
_STT_MODEL = "scribe_v2"
_TTS_MODEL = "eleven_flash_v2_5"
_VOICE = "JBFqnCBsd6RMkjVDRZzb"


class ElevenLabsVoiceProvider:
    """One paid request per operation, using credentials from the current tenant scope.

    A successful TTS admission meters the complete submitted character count, including when
    playback is interrupted. Bytes heard are not a reliable measure of upstream billing.
    Network failures before response headers are explicitly unknown, never silently retried.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 30.0,
        max_audio_bytes: int = 5_760_000,
    ) -> None:
        if not math.isfinite(timeout_s) or not 0 < timeout_s <= 120:
            raise ValueError("Voice deadline must be positive and at most 120 seconds.")
        if not 2 <= max_audio_bytes <= 5_760_000:
            raise ValueError("Voice output limit must be between 2 and 5760000 bytes.")
        self._client = client
        self._timeout_s = timeout_s
        self._max_audio_bytes = max_audio_bytes

    @asynccontextmanager
    async def _http(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient(timeout=self._timeout_s, follow_redirects=False) as client:
                yield client

    @asynccontextmanager
    async def _transcription_response(
        self, audio: RecordedAudio, key: str
    ) -> AsyncIterator[httpx.Response]:
        async with (
            self._http() as client,
            asyncio.timeout(self._timeout_s),
            client.stream(
                "POST",
                f"{_BASE}/speech-to-text",
                headers={"xi-api-key": key},
                data={"model_id": _STT_MODEL, "tag_audio_events": "false", "diarize": "false"},
                files={"file": ("recording.wav", audio.data, "audio/wav")},
                follow_redirects=False,
            ) as response,
        ):
            yield response

    @asynccontextmanager
    async def _speech_response(self, text: str, key: str) -> AsyncIterator[httpx.Response]:
        async with (
            self._http() as client,
            asyncio.timeout(self._timeout_s),
            client.stream(
                "POST",
                f"{_BASE}/text-to-speech/{_VOICE}/stream",
                params={"output_format": "pcm_24000"},
                headers={"xi-api-key": key, "accept": "audio/pcm"},
                json={"text": text, "model_id": _TTS_MODEL},
                follow_redirects=False,
            ) as response,
        ):
            yield response

    async def transcribe(self, audio: RecordedAudio, *, run_id: str) -> Transcription:
        validated = read_audio(audio.data)
        key = _key()
        operation = _ProviderOperation("stt", _STT_MODEL, run_id)
        outcome = "unknown"
        try:
            async with self._transcription_response(validated, key) as response:
                outcome = _accepted(response)
                return await _transcription(response)
        except _ProviderRefusalError as exc:
            outcome = exc.outcome
            raise
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise VoiceError(
                "Transcription is unavailable. You can type your answer.", status_code=502
            ) from None
        finally:
            _meter(operation, outcome, {CostUnit.AUDIO_SECONDS: validated.duration_s})

    async def speak(self, text: str, *, run_id: str) -> AsyncIterator[bytes]:
        if not text.strip() or len(text) > 8000:
            raise VoiceError("Speech text is empty or exceeds the limit.", status_code=422)
        spoken = spoken_text(text)
        key = _key()
        operation = _ProviderOperation("tts", _TTS_MODEL, run_id)
        outcome = "unknown"
        try:
            async with self._speech_response(spoken, key) as response:
                outcome = _accepted(response)
                async for chunk in _pcm_chunks(response, self._max_audio_bytes):
                    yield chunk
        except _ProviderRefusalError as exc:
            outcome = exc.outcome
            raise
        except (httpx.HTTPError, TimeoutError):
            raise VoiceError(
                "Speech is unavailable. Read the text response.", status_code=502
            ) from None
        finally:
            _meter(operation, outcome, {CostUnit.CHARS: len(spoken)})


async def _transcription(response: httpx.Response) -> Transcription:
    payload = bytearray()
    async for chunk in response.aiter_bytes():
        payload.extend(chunk)
        if len(payload) > 262144:
            raise VoiceError("Transcription response exceeds the limit.", status_code=502)
    data = json.loads(payload)
    text = data.get("text") if isinstance(data, dict) else None
    if not isinstance(text, str) or len(text) > 4000 or not text.strip():
        raise VoiceError(
            "No usable speech was recognized. You can type your answer.", status_code=422
        )
    return Transcription(text=text, provider="elevenlabs", model=_STT_MODEL)


async def _pcm_chunks(response: httpx.Response, limit: int) -> AsyncIterator[bytes]:
    media_type = response.headers.get("content-type", "application/octet-stream").split(";")[0]
    if media_type not in {"audio/pcm", "audio/raw", "application/octet-stream"}:
        raise VoiceError("Speech format is unavailable. Read the text response.", status_code=502)
    received = 0
    pending = b""
    async for chunk in response.aiter_bytes():
        received += len(chunk)
        if received > limit:
            raise VoiceError("Speech exceeded the playback limit.", status_code=502)
        pending += chunk
        aligned = len(pending) - len(pending) % 2
        if aligned:
            yield pending[:aligned]
            pending = pending[aligned:]
    if pending or not received:
        raise VoiceError("Speech ended unexpectedly. Read the text response.", status_code=502)


def _key() -> str:
    key = resolve_secret("ELEVENLABS_API_KEY")
    if not key:
        raise VoiceError("Add an ElevenLabs key in Settings to use voice.", status_code=503)
    return key


def _accepted(response: httpx.Response) -> str:
    # Keep provider response bodies (which can echo submitted text or credentials) out of errors.
    if response.is_success:
        return "accepted"
    raise _ProviderRefusalError("rejected" if 400 <= response.status_code < 500 else "unknown")


class _ProviderRefusalError(VoiceError):
    def __init__(self, outcome: str) -> None:
        super().__init__(
            "The voice provider declined the request. Continue with text.", status_code=502
        )
        self.outcome = outcome


@dataclass(frozen=True)
class _ProviderOperation:
    kind: str
    model: str
    run_id: str


def _meter(operation: _ProviderOperation, outcome: str, usage: dict[CostUnit, float]) -> None:
    record_cost(
        component=f"live_voice_{operation.kind}" + ("" if outcome == "accepted" else f"_{outcome}"),
        provider=CostProvider.ELEVENLABS,
        model=operation.model,
        usage=usage if outcome == "accepted" else {},
        rate_policy=RatePolicy.EXACT_MODEL,
    )
    _logger.info(
        "live.voice.provider", run_id=operation.run_id, operation=operation.kind, outcome=outcome
    )
