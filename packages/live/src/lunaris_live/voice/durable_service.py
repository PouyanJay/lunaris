import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, suppress

import structlog

from .error import VoiceError
from .models.dependencies import VoiceDependencies
from .models.operation import VoiceOperation
from .models.policy import VoicePolicy
from .models.recorded_audio import RecordedAudio
from .persistence.models.claim import VoiceClaim
from .persistence.schemas.result import VoiceResult
from .providers.pronunciation import spoken_text
from .read_audio import read_audio
from .schemas.source import VoiceSource
from .schemas.transcript import VoiceTranscript
from .speech_stream import SpeechStream


class DurableVoiceService:
    """Adapt the current learning turn; one durable admission for each explicit paid attempt."""

    def __init__(
        self, dependencies: VoiceDependencies, *, policy: VoicePolicy | None = None
    ) -> None:
        self._deps = dependencies
        self._policy = policy or VoicePolicy()
        self._cleanup_tasks: set[asyncio.Task[None]] = set()

    async def transcribe(self, operation: VoiceOperation, data: bytes) -> VoiceTranscript:
        audio = read_audio(data)
        claim = await self._deps.ledger.claim(
            operation,
            kind="transcription",
            fingerprint=hashlib.sha256(data).hexdigest(),
            reserve_usd=self._reservation(audio.duration_s * self._policy.stt_reserve_per_second),
        )
        self._require_available(claim)
        if claim.status == "completed":
            return self._transcript(operation, claim.result)
        return await self._transcribe_admitted(operation, audio, claim)

    async def _transcribe_admitted(
        self, operation: VoiceOperation, audio: RecordedAudio, claim: VoiceClaim
    ) -> VoiceTranscript:
        completed = False
        try:
            async with asyncio.timeout(self._policy.operation_timeout_s):
                result = await self._deps.provider.transcribe(audio, run_id=operation.run_id)
                stored = VoiceResult(text=result.text, provider=result.provider, model=result.model)
                completed = await self._deps.ledger.complete(operation, claim.token, stored)
                self._require_current(completed)
                return self._transcript(operation, stored)
        except (VoiceError, asyncio.CancelledError):
            raise
        except Exception:
            raise VoiceError(
                "Transcription is unavailable. You can type your answer.", status_code=502
            ) from None
        finally:
            if not completed:
                await self._cleanup(operation, claim)

    async def speech(self, operation: VoiceOperation) -> AsyncIterator[bytes]:
        text = await self._speech_text(operation)
        claim = await self._deps.ledger.claim(
            operation,
            kind="speech",
            fingerprint=self._speech_fingerprint(text),
            reserve_usd=self._reservation(
                len(spoken_text(text)) * self._policy.tts_reserve_per_char
            ),
        )
        self._require_available(claim)
        if claim.status == "completed":
            return self._replay_audio(claim.result)
        if claim.source_text != text:
            await self._cleanup(operation, claim)
            raise VoiceError("The speech source has changed. Use the current turn.")
        return SpeechStream(
            self._stream_audio(operation, claim), lambda: self._cleanup(operation, claim)
        )

    def _speech_fingerprint(self, text: str) -> str:
        return hashlib.sha256(
            json.dumps(
                [
                    self._policy.voice_version,
                    self._policy.speech_provider,
                    self._policy.speech_model,
                    text,
                ]
            ).encode()
        ).hexdigest()

    async def _speech_text(self, operation: VoiceOperation) -> str:
        session = await self._deps.sessions.load(operation.session_id, owner_id=operation.owner_id)
        if not session.turns:
            raise VoiceError("This session has no speech response.")
        turn = session.turns[-1]
        if (turn.seq, turn.run_id) != (operation.turn_seq, operation.source_run_id):
            raise VoiceError("The session has moved on. Use the current turn.")
        if operation.exchange_sequence is not None:
            if (
                not 1 <= operation.exchange_sequence <= 20
                or len(turn.sim_exchanges) != operation.exchange_sequence
            ):
                raise VoiceError("This simulator reaction is no longer current.")
            text = turn.sim_exchanges[-1].reaction.text
        else:
            text = turn.tutor
        if not text.strip() or len(text) > 4000:
            raise VoiceError(
                "This response cannot be spoken. Read the text instead.", status_code=422
            )
        return text

    async def _stream_audio(
        self, operation: VoiceOperation, claim: VoiceClaim
    ) -> AsyncGenerator[bytes, None]:
        completed = False
        try:
            async with asyncio.timeout(self._policy.operation_timeout_s):
                chunks = bytearray()
                provider_chunks = self._provider_chunks(operation, claim, chunks)
                async with aclosing(provider_chunks):
                    async for chunk in provider_chunks:
                        yield chunk
                completed = await self._cache_audio(operation, claim, bytes(chunks))
        except (VoiceError, asyncio.CancelledError):
            raise
        except Exception:
            raise VoiceError(
                "Speech is unavailable. Read the text response.", status_code=502
            ) from None
        finally:
            if not completed:
                await self._cleanup(operation, claim)

    async def _provider_chunks(
        self, operation: VoiceOperation, claim: VoiceClaim, chunks: bytearray
    ) -> AsyncIterator[bytes]:
        upstream = self._deps.provider.speak(claim.source_text, run_id=operation.run_id)
        try:
            async for chunk in upstream:
                self._validate_chunk(chunk, len(chunks))
                chunks.extend(chunk)
                if chunk:
                    yield chunk
        finally:
            close = getattr(upstream, "aclose", None)
            if close is not None:
                await close()

    async def _cache_audio(self, operation: VoiceOperation, claim: VoiceClaim, pcm: bytes) -> bool:
        if not pcm or len(pcm) % 2:
            raise VoiceError("Speech ended unexpectedly. Read the text response.", status_code=502)
        await self._deps.audio.put(claim.audio_key, pcm)
        result = self._audio_result(claim, len(pcm))
        completed = await self._deps.ledger.complete(operation, claim.token, result)
        self._require_current(completed)
        return completed

    async def _replay_audio(self, result: VoiceResult | None) -> AsyncIterator[bytes]:
        pcm = await self._cached_pcm(result)
        for offset in range(0, len(pcm), 65536):
            yield pcm[offset : offset + 65536]

    async def _cached_pcm(self, result: VoiceResult | None) -> bytes:
        try:
            if result is None or result.audio_key is None:
                raise ValueError("Missing speech metadata")
            async with asyncio.timeout(self._policy.operation_timeout_s):
                pcm = await self._deps.audio.get(result.audio_key)
            if len(pcm) != result.audio_bytes or len(pcm) > self._policy.max_audio_bytes:
                raise ValueError("Invalid cached PCM")
            return pcm
        except Exception:
            raise VoiceError(
                "Stored speech is unavailable. Read the text instead.", status_code=503
            ) from None

    def _audio_result(self, claim: VoiceClaim, count: int) -> VoiceResult:
        return VoiceResult(
            audio_key=claim.audio_key,
            audio_bytes=count,
            sample_rate=24000,
            provider=self._policy.speech_provider,
            model=self._policy.speech_model,
        )

    def _validate_chunk(self, chunk: bytes, count: int) -> None:
        if not isinstance(chunk, bytes) or count + len(chunk) > self._policy.max_audio_bytes:
            raise VoiceError("Speech exceeded the playback limit.", status_code=502)

    def _reservation(self, amount: float) -> float:
        if amount > 3:
            raise VoiceError(
                "This voice request exceeds the session voice budget.", status_code=429
            )
        return amount

    @staticmethod
    def _transcript(operation: VoiceOperation, result: VoiceResult | None) -> VoiceTranscript:
        if result is None or result.text is None:
            raise VoiceError(
                "Stored transcription is unavailable. Type your answer.", status_code=503
            )
        return VoiceTranscript(
            text=result.text,
            source=VoiceSource(turn_seq=operation.turn_seq, run_id=operation.source_run_id),
            operation_id=operation.operation_id,
            provider=result.provider,
            model=result.model,
        )

    @staticmethod
    def _require_available(claim: VoiceClaim) -> None:
        if claim.status not in ("started", "completed"):
            raise VoiceError(
                "This voice attempt cannot be repeated. Continue with text.", status_code=409
            )
        if claim.status == "started" and claim.token is None:
            raise VoiceError("Voice admission is unavailable.", status_code=503)

    @staticmethod
    def _require_current(completed: bool) -> None:
        if not completed:
            raise VoiceError("The session has moved on. Use the current turn.")

    async def _cleanup(self, operation: VoiceOperation, claim: VoiceClaim) -> None:
        task = asyncio.create_task(self._cleanup_once(operation, claim))
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)
        # A second disconnect must not cancel the bounded storage cleanup task.
        with suppress(asyncio.CancelledError):
            await asyncio.shield(task)

    async def _cleanup_once(self, operation: VoiceOperation, claim: VoiceClaim) -> None:
        try:
            async with asyncio.timeout(self._policy.cleanup_timeout_s):
                actions = [self._deps.ledger.fail(operation, claim.token)]
                if claim.audio_key is not None:
                    actions.append(self._deps.audio.delete(claim.audio_key))
                results = await asyncio.gather(*actions, return_exceptions=True)
                if any(isinstance(result, BaseException) for result in results):
                    raise VoiceError("Cleanup deferred")
        except Exception:
            structlog.get_logger().warning(
                "live.voice.cleanup_deferred",
                session_id=operation.session_id,
                run_id=operation.run_id,
            )
