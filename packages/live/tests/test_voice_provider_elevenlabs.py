import asyncio
import io
import json
import wave
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from lunaris_live.voice.error import VoiceError
from lunaris_live.voice.models.recorded_audio import RecordedAudio
from lunaris_live.voice.providers.elevenlabs import ElevenLabsVoiceProvider
from lunaris_live.voice.read_audio import read_audio
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.metering.cost_scope import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostPocket, CostSubjectType
from structlog.testing import capture_logs


def recording() -> RecordedAudio:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "NONE"))
        wav.writeframes(b"\x00\x00" * 1600)
    return read_audio(buffer.getvalue())


def scope() -> CostScope:
    return CostScope(
        run_id="voice-provider-test",
        subject_type=CostSubjectType.LIVE_SESSION,
        subject_id="session",
        price_book=PriceBook.current(),
    )


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], fail: bool = False) -> None:
        self.chunks = chunks
        self.fail = fail
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk
        if self.fail:
            raise httpx.ReadError("secret-provider-body")

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("transcript", ["HIPAA and EHR.", "x" * 4000])
async def test_transcription_posts_valid_wav_and_preserves_text_and_provenance(
    transcript: str,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"text": transcript})

    meter = scope()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}), cost_scope(meter):
            result = await ElevenLabsVoiceProvider(client=client).transcribe(
                recording(), run_id=meter.run_id
            )
    assert result.text == transcript
    assert (result.provider, result.model) == ("elevenlabs", "scribe_v2")
    assert requests[0].headers["xi-api-key"] == "tenant-key"
    assert b"RIFF" in requests[0].content and b"scribe_v2" in requests[0].content
    assert meter.entries[0].usage == {"audio_seconds": 0.1}
    assert meter.entries[0].pocket == CostPocket.USER_KEY


@pytest.mark.asyncio
async def test_tts_streams_aligned_pcm_and_changes_only_spoken_pronunciation() -> None:
    stream = Chunks([b"\x01", b"\x02\x03", b"\x04"])
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, stream=stream, headers={"content-type": "audio/pcm"})

    meter = scope()
    text = "HIPAA and EHR."
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}), cost_scope(meter):
            chunks = [
                chunk
                async for chunk in ElevenLabsVoiceProvider(client=client).speak(
                    text, run_id=meter.run_id
                )
            ]
    assert chunks == [b"\x01\x02", b"\x03\x04"]
    assert text == "HIPAA and EHR."
    assert json.loads(requests[0].content)["text"] == "Hippa and E-H-R."
    assert requests[0].url.path.endswith("/JBFqnCBsd6RMkjVDRZzb/stream")
    assert requests[0].url.params["output_format"] == "pcm_24000"
    assert stream.closed
    assert meter.entries[0].usage == {"chars": len("Hippa and E-H-R.")}


@pytest.mark.asyncio
async def test_missing_tenant_key_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "platform-secret")
    requests: list[httpx.Request] = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: requests.append(r))
    ) as client:
        with run_credentials({}), pytest.raises(VoiceError, match="ElevenLabs"):
            await ElevenLabsVoiceProvider(client=client).transcribe(recording(), run_id="missing")
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 429, 500])
async def test_refusal_is_safe_and_never_retried(status: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, text="secret-provider-body")

    meter = scope()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}), cost_scope(meter):
            with pytest.raises(VoiceError) as error:
                await ElevenLabsVoiceProvider(client=client).transcribe(
                    recording(), run_id="refusal"
                )
    assert "secret-provider-body" not in str(error.value)
    assert len(requests) == 1
    assert meter.entries[0].component.endswith("_rejected" if status < 500 else "_unknown")
    assert meter.entries[0].usage == {}


@pytest.mark.asyncio
async def test_cancelling_stream_closes_upstream_and_preserves_accepted_usage() -> None:
    stream = Chunks([b"\x01\x02", b"\x03\x04"])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=stream))
    ) as client:
        meter = scope()
        with run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}), cost_scope(meter):
            speech = ElevenLabsVoiceProvider(client=client).speak("hello", run_id="cancel")
            assert await anext(speech) == b"\x01\x02"
            await speech.aclose()
    assert stream.closed
    assert meter.entries[0].usage == {"chars": 5}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks,fail,limit", [([b"123"], False, 10), ([b"12"], True, 10), ([b"123456"], False, 4)]
)
async def test_broken_or_oversized_audio_fails_without_retries(
    chunks: list[bytes], fail: bool, limit: int
) -> None:
    stream = Chunks(chunks, fail)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=stream))
    ) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}), pytest.raises(VoiceError):
            _ = [
                chunk
                async for chunk in ElevenLabsVoiceProvider(
                    client=client, max_audio_bytes=limit
                ).speak("hello", run_id="broken")
            ]
    assert stream.closed


@pytest.mark.asyncio
async def test_total_deadline_cancels_provider_without_retry() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        await asyncio.sleep(1)
        return httpx.Response(200, json={"text": "late"})

    meter = scope()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}),
            cost_scope(meter),
            pytest.raises(VoiceError),
        ):
            await ElevenLabsVoiceProvider(client=client, timeout_s=0.01).transcribe(
                recording(), run_id="timeout"
            )
    assert len(requests) == 1
    assert meter.entries[0].component.endswith("_unknown")


@pytest.mark.asyncio
async def test_unknown_voice_model_price_preserves_units_without_flat_placeholder() -> None:
    meter = scope()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"12"))
    ) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}), cost_scope(meter):
            _ = [
                chunk
                async for chunk in ElevenLabsVoiceProvider(client=client).speak(
                    "hello", run_id="unpriced"
                )
            ]
    assert meter.entries[0].usage == {"chars": 5}
    assert meter.entries[0].amount == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"text": ""}, {"text": 12}, {"text": "x" * 4001}, []])
async def test_invalid_transcript_is_safe_and_retains_accepted_usage(payload: Any) -> None:
    meter = scope()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    ) as client:
        with (
            run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}),
            cost_scope(meter),
            pytest.raises(VoiceError),
        ):
            await ElevenLabsVoiceProvider(client=client).transcribe(recording(), run_id="invalid")
    assert meter.entries[0].usage == {"audio_seconds": 0.1}


@pytest.mark.asyncio
async def test_wrong_media_type_is_not_delivered() -> None:
    response = httpx.Response(200, content=b"12", headers={"content-type": "audio/mpeg"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response)) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}), pytest.raises(VoiceError):
            await anext(ElevenLabsVoiceProvider(client=client).speak("hello", run_id="format"))


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", "x" * 8001])
async def test_invalid_text_rejected_before_provider_or_meter(text: str) -> None:
    calls: list[httpx.Request] = []
    meter = scope()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: calls.append(r))
    ) as client:
        with (
            run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}),
            cost_scope(meter),
            pytest.raises(VoiceError),
        ):
            await anext(ElevenLabsVoiceProvider(client=client).speak(text, run_id="invalid"))
    assert calls == []
    assert meter.entries == []


@pytest.mark.asyncio
async def test_provider_logs_correlation_without_content_or_credentials() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="private-transcript"))
    ) as client:
        with capture_logs() as logs, run_credentials({"ELEVENLABS_API_KEY": "private-key"}):
            with pytest.raises(VoiceError):
                await ElevenLabsVoiceProvider(client=client).transcribe(
                    recording(), run_id="trace-voice"
                )
    provider_logs = [entry for entry in logs if entry["event"] == "live.voice.provider"]
    assert provider_logs == [
        {
            "event": "live.voice.provider",
            "run_id": "trace-voice",
            "operation": "stt",
            "outcome": "unknown",
            "log_level": "info",
        }
    ]
    assert "private-" not in json.dumps(logs)


@pytest.mark.asyncio
async def test_task_cancellation_during_stt_records_unknown_and_propagates() -> None:
    started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    meter = scope()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with run_credentials({"ELEVENLABS_API_KEY": "tenant-key"}), cost_scope(meter):
            task = asyncio.create_task(
                ElevenLabsVoiceProvider(client=client).transcribe(recording(), run_id="cancel-stt")
            )
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert meter.entries[0].component == "live_voice_stt_unknown"
    assert meter.entries[0].usage == {}
