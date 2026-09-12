from pydantic import Field

from ...graph.schema.base import LiveModel


class SimCandidate(LiveModel):
    html: str = Field(min_length=1, max_length=100_000)
