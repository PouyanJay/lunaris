from uuid import UUID

from pydantic import Field

from ....graph.schema.base import LiveModel
from .request import SimRequest


class SimJob(LiveModel):
    owner_id: UUID
    session_id: str = Field(min_length=1, max_length=100)
    cache_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    token: UUID
    request: SimRequest
