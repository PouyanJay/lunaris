from pydantic import Field

from ...graph.schema.base import LiveModel


class SimVisualVerdict(LiveModel):
    passed: bool = Field(strict=True)
    content_hash: str | None = None
    explanation: str = Field(min_length=1, max_length=2000)
