from uuid import UUID

from pydantic import Field

from ...graph.schema.base import LiveModel
from .source import VoiceSource


class VoiceTranscript(LiveModel):
    text: str = Field(max_length=4000)
    source: VoiceSource
    operation_id: UUID
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
