import math
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from ...models.operation import VoiceOperation


@dataclass(frozen=True)
class VoiceAdmission:
    """Internal validated request; the public ledger keeps its established call signature."""

    operation: VoiceOperation
    kind: Literal["transcription", "speech"]
    fingerprint: str
    reserve_usd: float

    def __post_init__(self) -> None:
        if (
            self.kind not in ("speech", "transcription")
            or not re.fullmatch("[a-f0-9]{64}", self.fingerprint)
            or not math.isfinite(self.reserve_usd)
            or not 0 < self.reserve_usd <= 3
        ):
            raise ValueError("Invalid voice admission request")

    @property
    def key(self) -> tuple[str, str | None, UUID]:
        return (self.operation.session_id, self.operation.owner_id, self.operation.operation_id)

    @property
    def source(self) -> tuple[int, str, int | None]:
        return (
            self.operation.turn_seq,
            self.operation.source_run_id,
            self.operation.exchange_sequence,
        )

    @property
    def identity(self) -> tuple[str, str, tuple[int, str, int | None]]:
        return self.kind, self.fingerprint, self.source
