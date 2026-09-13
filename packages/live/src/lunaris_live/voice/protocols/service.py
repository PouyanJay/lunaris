from collections.abc import AsyncIterator
from typing import Protocol

from ..models.operation import VoiceOperation
from ..schemas.transcript import VoiceTranscript


class IVoiceService(Protocol):
    async def transcribe(self, operation: VoiceOperation, data: bytes) -> VoiceTranscript: ...
    async def speech(self, operation: VoiceOperation) -> AsyncIterator[bytes]: ...
