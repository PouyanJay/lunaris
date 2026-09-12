from pydantic import Field

from ...graph.schema.base import LiveModel
from .teaching_spec import TeachingSpec


class SimPlanProposal(LiveModel):
    spec: TeachingSpec | None = None
    reason: str = Field(min_length=1, max_length=1000)
