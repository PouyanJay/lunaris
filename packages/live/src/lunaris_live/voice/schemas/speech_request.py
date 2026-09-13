from uuid import UUID

from ...graph.schema.base import LiveModel
from .source import VoiceSource


class SpeechRequest(LiveModel):
    source: VoiceSource
    operation_id: UUID
