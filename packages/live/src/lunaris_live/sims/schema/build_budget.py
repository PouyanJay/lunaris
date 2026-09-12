from pydantic import Field

from ...graph.schema.base import LiveModel


class SimBuildBudget(LiveModel):
    attempts: int = Field(default=2, ge=1, le=3, strict=True)
    deadline_s: float = Field(default=180, gt=0, le=240, allow_inf_nan=False)
    call_deadline_s: float = Field(default=60, gt=0, le=60, allow_inf_nan=False)
    output_tokens: int = Field(default=6000, ge=256, le=8000, strict=True)
    token_reservation: int = Field(default=80_000, ge=1, le=100_000, strict=True)
