import io
import wave
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from lunaris_live.session.memory_session_store import MemorySessionStore
from lunaris_live.session.schema import Session, SessionTurn
from lunaris_live.voice.durable_service import DurableVoiceService
from lunaris_live.voice.models.dependencies import VoiceDependencies
from lunaris_live.voice.models.operation import VoiceOperation
from lunaris_live.voice.models.transcription import Transcription
from lunaris_live.voice.persistence.memory_audio_store import MemoryVoiceAudioStore
from lunaris_live.voice.persistence.memory_ledger import MemoryVoiceLedger


def recording(value=b"\0\0") -> bytes:
    data = io.BytesIO()
    with wave.open(data, "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        out.writeframes(value * 16000)
    return data.getvalue()


class Provider:
    def __init__(self) -> None:
        self.transcriptions = 0
        self.speeches = 0
        self.ended = False

    async def transcribe(self, audio, *, run_id):
        self.transcriptions += 1
        return Transcription("My answer", "test", "test")

    async def speak(self, text, *, run_id) -> AsyncIterator[bytes]:
        self.speeches += 1
        try:
            yield b"\0\1"
            yield b"\2\3"
        finally:
            self.ended = True


class Sessions:
    def __init__(self, store):
        self.store = store

    async def load(self, sid, *, owner_id):
        return self.store.load(sid, owner_id=owner_id)


def system(provider=None):
    store = MemorySessionStore()
    store.save(
        Session(
            session_id="s",
            graph_id="g",
            started_at=datetime.now(UTC),
            turns=[
                SessionTurn(
                    seq=1,
                    run_id="r",
                    tutor="Try this.",
                    move={"kind": "introduce", "reason": "start"},
                )
            ],
        )
    )
    ledger = MemoryVoiceLedger(store)
    audio = MemoryVoiceAudioStore()
    provider = provider or Provider()
    dependencies = VoiceDependencies(
        ledger=ledger, audio=audio, provider=provider, sessions=Sessions(store)
    )
    return DurableVoiceService(dependencies), provider, store, ledger, audio


def operation():
    return VoiceOperation("s", None, uuid4(), "request", 1, "r")


@pytest.mark.asyncio
async def test_transcription_replays_without_second_provider_call_or_learning_mutation():
    service, provider, sessions, _, _ = system()
    op = operation()
    before = sessions.load("s").model_dump()
    first = await service.transcribe(op, recording())
    replay = await service.transcribe(op, recording())
    assert first == replay
    assert first.text == "My answer" and first.provider == "test"
    assert provider.transcriptions == 1
    assert sessions.load("s").model_dump() == before


@pytest.mark.asyncio
async def test_speech_streams_before_eof_and_replays_identical_pcm_without_provider():
    service, provider, _, _, _ = system()
    op = operation()
    stream = await service.speech(op)
    first = await anext(stream)
    assert first == b"\0\1" and not provider.ended
    result = first + b"".join([chunk async for chunk in stream])
    replay = await service.speech(op)
    assert b"".join([chunk async for chunk in replay]) == result
    assert provider.speeches == 1 and provider.ended


@pytest.mark.asyncio
async def test_invalid_recording_and_changed_attempt_payload_never_bill_again():
    from lunaris_live.voice.error import VoiceError

    service, provider, _, _, _ = system()
    op = operation()
    with pytest.raises(VoiceError):
        await service.transcribe(op, b"not a wav")
    assert provider.transcriptions == 0
    await service.transcribe(op, recording())
    with pytest.raises(VoiceError):
        await service.transcribe(op, recording(b"\1\0"))
    assert provider.transcriptions == 1


@pytest.mark.asyncio
async def test_concurrent_same_attempt_admits_once_and_cancellation_is_not_retried():
    import asyncio

    from lunaris_live.voice.error import VoiceError

    class Waiting(Provider):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def transcribe(self, audio, *, run_id):
            self.transcriptions += 1
            self.started.set()
            await self.release.wait()
            return Transcription("Answer", "test", "test")

    provider = Waiting()
    service, _, _, _, _ = system(provider)
    op = operation()
    first = asyncio.create_task(service.transcribe(op, recording()))
    await provider.started.wait()
    with pytest.raises(VoiceError):
        await service.transcribe(op, recording())
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    with pytest.raises(VoiceError):
        await service.transcribe(op, recording())
    assert provider.transcriptions == 1


@pytest.mark.asyncio
async def test_stale_transcription_is_not_returned_or_retried():
    from lunaris_live.voice.error import VoiceError

    class Advances(Provider):
        async def transcribe(self, audio, *, run_id):
            result = await super().transcribe(audio, run_id=run_id)
            current = sessions.load("s")
            sessions.save(
                current.model_copy(
                    update={"turns": [current.turns[-1].model_copy(update={"seq": 2})]}
                )
            )
            return result

    service, provider, sessions, _, _ = system(Advances())
    with pytest.raises(VoiceError):
        await service.transcribe(operation(), recording())
    assert provider.transcriptions == 1


@pytest.mark.asyncio
async def test_stream_close_stops_upstream_and_prevents_paid_replay():
    from lunaris_live.voice.error import VoiceError

    service, provider, _, _, _ = system()
    op = operation()
    stream = await service.speech(op)
    await anext(stream)
    await stream.aclose()
    assert provider.ended
    with pytest.raises(VoiceError):
        await service.speech(op)
    assert provider.speeches == 1


@pytest.mark.asyncio
async def test_closing_unconsumed_stream_releases_admission_without_provider_call():
    from lunaris_live.voice.persistence.models.limits import VoiceLimits

    _, provider, sessions, _, audio = system()
    ledger = MemoryVoiceLedger(sessions, limits=VoiceLimits(concurrency=1))
    service = DurableVoiceService(VoiceDependencies(ledger, audio, provider, Sessions(sessions)))
    stream = await service.speech(operation())
    await stream.aclose()
    next_stream = await service.speech(operation())
    await next_stream.aclose()
    assert provider.speeches == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [[], [b"\0"], [b"\0\0", b"\1\1\1\1"]])
async def test_invalid_or_oversized_pcm_is_not_cached_or_retried(chunks):
    from lunaris_live.voice.error import VoiceError
    from lunaris_live.voice.models.policy import VoicePolicy

    class Invalid(Provider):
        async def speak(self, text, *, run_id):
            self.speeches += 1
            for chunk in chunks:
                yield chunk

    _, provider, sessions, ledger, audio = system(Invalid())
    service = DurableVoiceService(
        VoiceDependencies(ledger, audio, provider, Sessions(sessions)),
        policy=VoicePolicy(max_audio_bytes=4),
    )
    op = operation()
    stream = await service.speech(op)
    with pytest.raises(VoiceError):
        _ = [chunk async for chunk in stream]
    with pytest.raises(VoiceError):
        await service.speech(op)
    assert provider.speeches == 1


@pytest.mark.asyncio
async def test_session_deleted_during_stream_removes_generated_audio_and_refuses_completion():
    from lunaris_live.voice.error import VoiceError

    class Audio(MemoryVoiceAudioStore):
        key = None

        async def put(self, key, pcm):
            self.key = key
            await super().put(key, pcm)

    _, provider, sessions, ledger, _ = system()
    audio = Audio()
    service = DurableVoiceService(VoiceDependencies(ledger, audio, provider, Sessions(sessions)))
    stream = await service.speech(operation())
    await anext(stream)
    sessions.delete("s")
    with pytest.raises(VoiceError):
        _ = [chunk async for chunk in stream]
    assert audio.key is not None
    with pytest.raises(FileNotFoundError):
        await audio.get(audio.key)
    assert provider.ended


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_fails", [False, True])
async def test_failed_cache_write_never_retries_provider_even_when_cleanup_fails(delete_fails):
    from lunaris_live.voice.error import VoiceError

    class Audio(MemoryVoiceAudioStore):
        async def put(self, key, pcm):
            await super().put(key, pcm)
            raise RuntimeError("private storage diagnostic")

        async def delete(self, key):
            if delete_fails:
                raise RuntimeError("private storage diagnostic")
            await super().delete(key)

    _, provider, sessions, ledger, _ = system()
    service = DurableVoiceService(VoiceDependencies(ledger, Audio(), provider, Sessions(sessions)))
    op = operation()
    stream = await service.speech(op)
    with pytest.raises(VoiceError) as failure:
        _ = [chunk async for chunk in stream]
    assert "private storage diagnostic" not in str(failure.value)
    with pytest.raises(VoiceError):
        await service.speech(op)
    assert provider.speeches == 1


@pytest.mark.asyncio
async def test_text_changed_between_preflight_and_admission_never_reaches_provider():
    from lunaris_live.voice.error import VoiceError

    _, provider, sessions, ledger, audio = system()

    class Changes(Sessions):
        async def load(self, sid, *, owner_id):
            previous = await super().load(sid, owner_id=owner_id)
            changed = previous.turns[-1].model_copy(update={"tutor": "A different response"})
            sessions.save(previous.model_copy(update={"turns": [changed]}))
            return previous

    service = DurableVoiceService(VoiceDependencies(ledger, audio, provider, Changes(sessions)))
    with pytest.raises(VoiceError):
        await service.speech(operation())
    assert provider.speeches == 0


@pytest.mark.asyncio
async def test_speech_reservation_accounts_for_expanded_pronunciation_aliases():
    from lunaris_live.voice.error import VoiceError
    from lunaris_live.voice.persistence.models.limits import VoiceLimits
    from lunaris_live.voice.providers.pronunciation import spoken_text

    _, provider, sessions, _, audio = system()
    current = sessions.load("s")
    sessions.save(
        current.model_copy(
            update={"turns": [current.turns[-1].model_copy(update={"tutor": "EHR"})]}
        )
    )
    assert len(spoken_text("EHR")) > len("EHR")
    ledger = MemoryVoiceLedger(sessions, limits=VoiceLimits(reserve_usd=len("EHR") * 0.0003))
    service = DurableVoiceService(VoiceDependencies(ledger, audio, provider, Sessions(sessions)))
    with pytest.raises(VoiceError):
        await service.speech(operation())
    assert provider.speeches == 0


@pytest.mark.asyncio
async def test_missing_cached_audio_refuses_safely_without_regeneration():
    from lunaris_live.voice.error import VoiceError

    class MissingAudio(MemoryVoiceAudioStore):
        async def get(self, key):
            raise FileNotFoundError("private key")

    _, provider, sessions, ledger, _ = system()
    service = DurableVoiceService(
        VoiceDependencies(ledger, MissingAudio(), provider, Sessions(sessions))
    )
    op = operation()
    first = await service.speech(op)
    _ = [chunk async for chunk in first]
    replay = await service.speech(op)
    with pytest.raises(VoiceError) as failure:
        _ = [chunk async for chunk in replay]
    assert "private key" not in str(failure.value)
    assert provider.speeches == 1


@pytest.mark.asyncio
async def test_provider_protocol_accepts_plain_async_iterator_without_close_method():
    class Iterator:
        def __init__(self):
            self.chunks = iter([b"\0\0", b"\1\1"])

        def __aiter__(self):
            return self

        async def __anext__(self):
            item = next(self.chunks, None)
            if item is None:
                raise StopAsyncIteration
            return item

    class Plain(Provider):
        def speak(self, text, *, run_id):
            self.speeches += 1
            return Iterator()

    service, provider, _, _, _ = system(Plain())
    stream = await service.speech(operation())
    assert b"".join([chunk async for chunk in stream]) == b"\0\0\1\1"
    assert provider.speeches == 1
