from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .teaching_spec import TeachingSpec


class SimPlanProposal(LiveModel):
    renderer: Literal["series-resistor-v1"] | None = None
    spec: TeachingSpec | None = None
    reason: str = Field(min_length=1, max_length=1000)
