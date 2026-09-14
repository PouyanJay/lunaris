from collections.abc import AsyncIterator
from datetime import UTC, datetime

import structlog

from ..session.schema import Session, SessionStatus, SessionTurn
from .error import VoiceError
from .models.operation import VoiceOperation
from .protocols.provider import IVoiceProvider
from .protocols.session_reader import IVoiceSessionReader
from .read_audio import read_audio
from .schemas.source import VoiceSource
from .schemas.transcript import VoiceTranscript


class VoiceService:
    """Read authorized speech sources without grading or advancing the session."""

    def __init__(
        self,
        sessions: IVoiceSessionReader,
        provider: IVoiceProvider,
        *,
        session_budget_s: float = 1800.0,
    ) -> None:
        self._sessions, self._provider = sessions, provider
        self._session_budget_s = session_budget_s

    async def _session(self, operation: VoiceOperation) -> Session:
        session = await self._sessions.load(operation.session_id, owner_id=operation.owner_id)
        if not session.turns or session.status == SessionStatus.ABANDONED:
            raise VoiceError("This session is not accepting voice.")
        if (
            session.status in (SessionStatus.ACTIVE, SessionStatus.PLACING)
            and (datetime.now(UTC) - session.started_at).total_seconds() >= self._session_budget_s
        ):
            raise VoiceError("This session has reached its time limit. Continue in a new session.")
        turn = session.turns[-1]
        if (turn.seq, turn.run_id) != (
            operation.turn_seq,
            operation.source_run_id,
        ) or turn.answer is not None:
            raise VoiceError("The session has moved on. Use the current turn.")
        return session

    def _speech_text(self, turn: SessionTurn, operation: VoiceOperation) -> str:
        if operation.exchange_sequence is not None:
            if operation.exchange_sequence != len(turn.sim_exchanges):
                raise VoiceError("This simulator reaction is no longer current.")
            return turn.sim_exchanges[-1].reaction.text
        return turn.tutor

    async def _recording_turn(self, operation: VoiceOperation) -> None:
        session = await self._session(operation)
        if (
            session.status not in (SessionStatus.ACTIVE, SessionStatus.PLACING)
            or operation.exchange_sequence is not None
        ):
            raise VoiceError("This session is not accepting answers.")

    async def transcribe(self, operation: VoiceOperation, data: bytes) -> VoiceTranscript:
        await self._recording_turn(operation)
        audio = read_audio(data)
        result = await self._provider.transcribe(audio, run_id=operation.run_id)
        await self._recording_turn(operation)
        transcript = VoiceTranscript(
            text=result.text,
            source=VoiceSource(turn_seq=operation.turn_seq, run_id=operation.source_run_id),
            operation_id=operation.operation_id,
            provider=result.provider,
            model=result.model,
        )
        structlog.get_logger().info(
            "live.voice.transcribed",
            session_id=operation.session_id,
            run_id=operation.run_id,
            duration_s=audio.duration_s,
        )
        return transcript

    async def speech(self, operation: VoiceOperation) -> AsyncIterator[bytes]:
        session = await self._session(operation)
        text = self._speech_text(session.turns[-1], operation)
        if len(text) > 4000:
            raise VoiceError(
                "This response is too long for voice. Read the text instead.", status_code=422
            )
        structlog.get_logger().info(
            "live.voice.speech_requested",
            session_id=operation.session_id,
            run_id=operation.run_id,
            operation_id=str(operation.operation_id),
        )
        return self._provider.speak(text, run_id=operation.run_id)
