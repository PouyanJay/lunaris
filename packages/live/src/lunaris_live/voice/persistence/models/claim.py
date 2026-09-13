from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from ..schemas.result import VoiceResult


@dataclass(frozen=True)
class VoiceClaim:
    status: Literal["started", "completed", "in_progress", "indeterminate", "unavailable"]
    token: UUID | None = None
    source_text: str | None = None
    result: VoiceResult | None = None
    audio_key: str | None = None
