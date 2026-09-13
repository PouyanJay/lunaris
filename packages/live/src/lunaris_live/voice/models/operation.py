from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class VoiceOperation:
    session_id: str
    owner_id: str | None
    operation_id: UUID
    run_id: str
    turn_seq: int
    source_run_id: str
    exchange_sequence: int | None = None
