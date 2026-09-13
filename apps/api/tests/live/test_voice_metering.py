import asyncio
from collections.abc import AsyncIterator

import anyio
import pytest
from lunaris_api.live.voice.metered_provider import MeteredVoiceProvider
from lunaris_api.live.voice.metering_context import VoiceMeteringContext
from lunaris_api.live.voice.metering_dependencies import VoiceMeteringDependencies
from lunaris_live.voice.error import VoiceError
from lunaris_live.voice.models.recorded_audio import RecordedAudio
from lunaris_live.voice.models.transcription import Transcription
from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.metering import record_cost
from lunaris_runtime.metering.rate_policy import RatePolicy
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemorySubjectCostStore
from lunaris_runtime.schema import CostPocket, CostProvider, CostSubjectType, CostUnit


class YieldingEventStore(InMemoryCostEventStore):
    async def append(self, *, events, owner_id=None):
        await anyio.lowlevel.checkpoint()
        await super().append(events=events, owner_id=owner_id)


class Provider:
    def __init__(self):
        self.keys = []
        self.closed = False
        self.entered = asyncio.Event()

    def meter(self):
        record_cost(
            component="live_voice_tts",
            provider=CostProvider.ELEVENLABS,
            model="eleven_flash_v2_5",
            usage={CostUnit.CHARS: 12},
            rate_policy=RatePolicy.EXACT_MODEL,
        )

    async def transcribe(self, audio, *, run_id):
        self.keys.append(resolve_secret("ELEVENLABS_API_KEY"))
        self.meter()
        if not self.keys[-1]:
            raise VoiceError("Missing voice key", status_code=503)
        return Transcription("draft", "elevenlabs", "fixture")

    async def speak(self, text, *, run_id) -> AsyncIterator[bytes]:
        self.keys.append(resolve_secret("ELEVENLABS_API_KEY"))
        try:
            yield b"\0\0"
            self.entered.set()
            await asyncio.Event().wait()
        finally:
            self.closed = True
            self.meter()


@pytest.mark.asyncio
async def test_tenant_scope_records_usage_and_never_falls_back(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "platform-fixture")
    events, costs = YieldingEventStore(), InMemorySubjectCostStore()
    provider = Provider()

    async def resolver(owner):
        return {"ELEVENLABS_API_KEY": "tenant-fixture"} if owner == "alice" else {}

    for owner in ("alice", "bob"):
        wrapped = MeteredVoiceProvider(
            provider,
            VoiceMeteringContext(owner, owner),
            VoiceMeteringDependencies(resolver, events, costs),
        )
        if owner == "alice":
            assert (
                await wrapped.transcribe(RecordedAudio(b"", 1), run_id="alice-run")
            ).text == "draft"
        else:
            with pytest.raises(VoiceError):
                await wrapped.transcribe(RecordedAudio(b"", 1), run_id="bob-run")
        rows = await events.list_for_subject(
            subject_type=CostSubjectType.LIVE_SESSION, subject_id=owner, owner_id=owner
        )
        assert len(rows) == 1
        assert rows[0].run_id == f"{owner}-run"
        assert rows[0].usage == {"chars": 12}
        assert rows[0].amount == 0  # Unknown Flash account pricing remains unknown.
        assert rows[0].model == "eleven_flash_v2_5"
        assert rows[0].price_book_version
        assert rows[0].pocket == (CostPocket.USER_KEY if owner == "alice" else CostPocket.PLATFORM)
        assert (
            await events.list_for_subject(
                subject_type=CostSubjectType.LIVE_SESSION, subject_id=owner, owner_id="other"
            )
            == []
        )
    assert provider.keys == ["tenant-fixture", None]
    assert resolve_secret("ELEVENLABS_API_KEY") == "platform-fixture"


@pytest.mark.asyncio
async def test_stream_close_drains_upstream_finally_under_cancel_scope():
    events, costs = YieldingEventStore(), InMemorySubjectCostStore()
    provider = Provider()
    wrapped = MeteredVoiceProvider(
        provider,
        VoiceMeteringContext("session", "owner"),
        VoiceMeteringDependencies(cost_event_store=events, subject_cost_store=costs),
    )
    with anyio.CancelScope() as scope:
        stream = wrapped.speak("private text", run_id="speech-run")
        assert await anext(stream) == b"\0\0"
        scope.cancel()
        await stream.aclose()
    assert provider.closed
    rows = await events.list_for_subject(
        subject_type=CostSubjectType.LIVE_SESSION, subject_id="session", owner_id="owner"
    )
    assert len(rows) == 1
    assert rows[0].run_id == "speech-run"
    assert (
        await costs.get(
            subject_type=CostSubjectType.LIVE_SESSION, subject_id="session", owner_id="owner"
        )
        is not None
    )


@pytest.mark.asyncio
async def test_budget_refuses_before_provider_call():
    from datetime import UTC, datetime

    from lunaris_runtime.schema import SubjectCost

    costs = InMemorySubjectCostStore()
    await costs.upsert(
        cost=SubjectCost(
            subject_type=CostSubjectType.LIVE_SESSION,
            subject_id="session",
            total_amount=3,
            currency="USD",
            breakdown={},
            price_book_version="fixture",
            updated_at=datetime.now(UTC),
        ),
        owner_id="owner",
    )
    provider = Provider()
    wrapped = MeteredVoiceProvider(
        provider,
        VoiceMeteringContext("session", "owner", 3),
        VoiceMeteringDependencies(subject_cost_store=costs),
    )
    with pytest.raises(VoiceError) as error:
        await wrapped.transcribe(RecordedAudio(b"", 1), run_id="refused")
    assert error.value.status_code == 429
    with pytest.raises(VoiceError):
        await anext(wrapped.speak("text", run_id="refused-speech"))
    assert provider.keys == []


@pytest.mark.asyncio
async def test_cancelled_consumer_persists_usage_before_cancellation_escapes():
    events, costs = YieldingEventStore(), InMemorySubjectCostStore()
    provider = Provider()
    wrapped = MeteredVoiceProvider(
        provider,
        VoiceMeteringContext("session", "owner"),
        VoiceMeteringDependencies(cost_event_store=events, subject_cost_store=costs),
    )

    async def consume():
        async for _ in wrapped.speak("private text", run_id="cancelled-run"):
            pass

    task = asyncio.create_task(consume())
    await provider.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.closed
    rows = await events.list_for_subject(
        subject_type=CostSubjectType.LIVE_SESSION, subject_id="session", owner_id="owner"
    )
    assert len(rows) == 1
    assert rows[0].run_id == "cancelled-run"


@pytest.mark.asyncio
async def test_real_provider_boundary_attributes_stt_provenance_and_correlation():
    import io
    import wave

    import httpx
    from lunaris_live.voice.providers.elevenlabs import ElevenLabsVoiceProvider
    from structlog.contextvars import bound_contextvars, get_contextvars

    wav = io.BytesIO()
    with wave.open(wav, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b"\0\0" * 16000)
    seen = []

    async def respond(request):
        seen.append((request.headers["xi-api-key"], get_contextvars()))
        return httpx.Response(200, json={"text": "review this draft"})

    async def resolver(owner):
        assert owner == "owner"
        return {"ELEVENLABS_API_KEY": "tenant-fixture"}

    events, costs = YieldingEventStore(), InMemorySubjectCostStore()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        wrapped = MeteredVoiceProvider(
            ElevenLabsVoiceProvider(client=client),
            VoiceMeteringContext("session", "owner"),
            VoiceMeteringDependencies(resolver, events, costs),
        )
        with bound_contextvars(request_id="request-fixture", run_id="stt-run"):
            transcript = await wrapped.transcribe(
                RecordedAudio(wav.getvalue(), 1), run_id="stt-run"
            )
    assert (transcript.text, transcript.provider, transcript.model) == (
        "review this draft",
        "elevenlabs",
        "scribe_v2",
    )
    assert seen == [("tenant-fixture", {"request_id": "request-fixture", "run_id": "stt-run"})]
    rows = await events.list_for_subject(
        subject_type=CostSubjectType.LIVE_SESSION, subject_id="session", owner_id="owner"
    )
    assert len(rows) == 1
    assert rows[0].usage == {"audio_seconds": 1}
    assert rows[0].pocket == CostPocket.USER_KEY
    assert rows[0].run_id == "stt-run"
    assert rows[0].provider == CostProvider.ELEVENLABS
