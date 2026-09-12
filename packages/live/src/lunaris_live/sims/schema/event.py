from typing import Annotated, Literal

from pydantic import Field

from ...graph.schema.base import LiveModel


class SimEvent(LiveModel):
    """Untrusted learner input, scoped to one staged instrument and monotonically numbered."""

    version: Literal[1]
    instance_id: str = Field(min_length=1, max_length=100)
    turn_seq: int = Field(ge=1, strict=True)
    sequence: int = Field(ge=1, le=20, strict=True)
    app_id: str = Field(min_length=1, max_length=100)
    kind: Literal["param_changed", "milestone_reached", "misconception_signal"]
    state: dict[str, Annotated[float, Field(strict=True, allow_inf_nan=False)]] = Field(
        min_length=1, max_length=8
    )
