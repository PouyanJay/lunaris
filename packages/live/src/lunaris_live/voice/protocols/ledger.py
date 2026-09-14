from typing import Literal, Protocol
from uuid import UUID

from ..models.operation import VoiceOperation
from ..persistence.models.claim import VoiceClaim
from ..persistence.schemas.result import VoiceResult


class IVoiceLedger(Protocol):
    async def claim(
        self,
        operation: VoiceOperation,
        *,
        kind: Literal["transcription", "speech"],
        fingerprint: str,
        reserve_usd: float,
    ) -> VoiceClaim: ...
    async def complete(
        self, operation: VoiceOperation, token: UUID, result: VoiceResult
    ) -> bool: ...
    async def fail(self, operation: VoiceOperation, token: UUID) -> bool: ...
