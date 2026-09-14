from pydantic import Field

from ...graph.schema.base import LiveModel


class VoiceSource(LiveModel):
    """A persisted tutor turn or its latest validated simulator reaction."""

    turn_seq: int = Field(ge=1)
    run_id: str = Field(min_length=1, max_length=100)
    exchange_sequence: int | None = Field(default=None, ge=1, le=20)
