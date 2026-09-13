from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from ...session.memory_session_store import MemorySessionStore
from ...session.schema import Session, SessionStatus
from ..error import VoiceError
from ..models.operation import VoiceOperation
from .models.admission import VoiceAdmission
from .models.claim import VoiceClaim
from .models.limits import VoiceLimits
from .record_claim import record_claim
from .schemas.result import VoiceResult


@dataclass(frozen=True)
class _Entry:
    admission: VoiceAdmission
    expires_at: datetime
    created_at: datetime
    token: UUID
    audio_key: str | None
    status: str = "started"
    result: VoiceResult | None = None


class MemoryVoiceLedger:
    """Session-lock-backed local parity; share one instance in the composition root."""

    def __init__(
        self,
        sessions: MemorySessionStore,
        *,
        limits: VoiceLimits | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessions, self._limits, self._clock = sessions, limits or VoiceLimits(), clock
        self._entries: dict[tuple[str, str | None, UUID], _Entry] = {}

    async def claim(
        self,
        operation: VoiceOperation,
        *,
        kind: Literal["transcription", "speech"],
        fingerprint: str,
        reserve_usd: float,
    ) -> VoiceClaim:
        self._scrub_results()
        admission = VoiceAdmission(operation, kind, fingerprint, reserve_usd)
        return record_claim(operation, self._claim(admission))

    def _scrub_results(self) -> None:
        now = self._clock()
        for key, entry in tuple(self._entries.items()):
            operation = entry.admission.operation
            try:
                with self._sessions.locked_session(
                    operation.session_id, owner_id=operation.owner_id
                ):
                    if entry.created_at + timedelta(days=1) <= now:
                        self._entries[key] = replace(entry, result=None)
            except FileNotFoundError:
                del self._entries[key]

    def _claim(self, admission: VoiceAdmission) -> VoiceClaim:
        operation = admission.operation
        with self._sessions.locked_session(
            operation.session_id, owner_id=operation.owner_id
        ) as session:
            text = self._source(session, admission)
            entries = self._session_entries(admission)
            existing = self._entries.get(admission.key)
            if existing is not None:
                return self._replay(existing, admission)
            if self._at_capacity(entries, admission.reserve_usd):
                return VoiceClaim("unavailable")
            return self._admit(admission, text)

    def _session_entries(self, admission: VoiceAdmission) -> list[_Entry]:
        entries = []
        now = self._clock()
        for key, entry in self._entries.items():
            if key[:2] != admission.key[:2]:
                continue
            if entry.status == "started" and entry.expires_at <= now:
                entry = replace(entry, status="indeterminate")
                self._entries[key] = entry
            entries.append(entry)
        return entries

    def _replay(self, entry: _Entry, admission: VoiceAdmission) -> VoiceClaim:
        if entry.admission.identity != admission.identity:
            raise VoiceError("This voice operation identifies another request.")
        if entry.status == "completed":
            if entry.created_at + timedelta(days=1) <= self._clock():
                return VoiceClaim("unavailable")
            return VoiceClaim("completed", result=entry.result)
        return VoiceClaim("in_progress" if entry.status == "started" else "indeterminate")

    def _at_capacity(self, entries: list[_Entry], reserve_usd: float) -> bool:
        return (
            len(entries) >= self._limits.operations
            or sum(entry.status == "started" for entry in entries) >= self._limits.concurrency
            or sum(entry.admission.reserve_usd for entry in entries) + reserve_usd
            > self._limits.reserve_usd
        )

    def _admit(self, admission: VoiceAdmission, text: str) -> VoiceClaim:
        now = self._clock()
        entry = _Entry(
            admission=admission,
            expires_at=now + timedelta(seconds=self._limits.lease_seconds),
            created_at=now,
            token=uuid4(),
            audio_key=f"{uuid4().hex}.pcm" if admission.kind == "speech" else None,
        )
        self._entries[admission.key] = entry
        return VoiceClaim("started", token=entry.token, source_text=text, audio_key=entry.audio_key)

    async def complete(self, operation: VoiceOperation, token: UUID, result: VoiceResult) -> bool:
        self._scrub_results()
        return self._finish(operation, token, result)

    async def fail(self, operation: VoiceOperation, token: UUID) -> bool:
        self._scrub_results()
        return self._finish(operation, token, None)

    def _finish(self, operation: VoiceOperation, token: UUID, result: VoiceResult | None) -> bool:
        try:
            with self._sessions.locked_session(
                operation.session_id, owner_id=operation.owner_id
            ) as session:
                entry = self._completion_entry(operation, token)
                if entry is None:
                    return False
                self._source(session, entry.admission)
                return self._publish(entry, result)
        except (FileNotFoundError, VoiceError):
            return False

    def _completion_entry(self, operation: VoiceOperation, token: UUID) -> _Entry | None:
        entry = self._entries.get(
            (operation.session_id, operation.owner_id, operation.operation_id)
        )
        if (
            entry is None
            or entry.token != token
            or entry.status != "started"
            or entry.expires_at <= self._clock()
        ):
            return None
        source = (operation.turn_seq, operation.source_run_id, operation.exchange_sequence)
        return entry if entry.admission.source == source else None

    def _publish(self, entry: _Entry, result: VoiceResult | None) -> bool:
        if result is not None and (
            (entry.admission.kind == "speech") != (result.audio_key is not None)
            or result.audio_key != entry.audio_key
        ):
            return False
        self._entries[entry.admission.key] = replace(
            entry, status="completed" if result is not None else "indeterminate", result=result
        )
        return True

    def _source(self, session: Session, admission: VoiceAdmission) -> str:
        self._validate_session(session, admission)
        operation = admission.operation
        turn = session.turns[-1]
        if (turn.seq, turn.run_id) != (
            operation.turn_seq,
            operation.source_run_id,
        ) or turn.answer is not None:
            raise VoiceError("The session has moved on. Use the current turn.")
        if operation.exchange_sequence is not None:
            if (
                not 1 <= operation.exchange_sequence <= 20
                or len(turn.sim_exchanges) != operation.exchange_sequence
            ):
                raise VoiceError("This simulator reaction is no longer current.")
            return turn.sim_exchanges[-1].reaction.text
        return turn.tutor

    def _validate_session(self, session: Session, admission: VoiceAdmission) -> None:
        if not session.turns or session.status == SessionStatus.ABANDONED:
            raise VoiceError("This session is not accepting voice.")
        active = session.status in (SessionStatus.ACTIVE, SessionStatus.PLACING)
        if (
            active
            and (self._clock() - session.started_at).total_seconds() >= self._limits.session_seconds
        ):
            raise VoiceError("This session has reached its time limit.")
        if admission.kind == "transcription" and (
            not active or admission.operation.exchange_sequence is not None
        ):
            raise VoiceError("This session is not accepting answers.")
