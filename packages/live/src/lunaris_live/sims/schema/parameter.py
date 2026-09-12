import math

from pydantic import Field, model_validator

from ...graph.schema.base import LiveModel


class SimParameter(LiveModel):
    """One bounded numeric control; booleans and nonfinite numbers are not positions."""

    label: str = Field(min_length=1, max_length=100)
    minimum: float = Field(allow_inf_nan=False, strict=True)
    maximum: float = Field(allow_inf_nan=False, strict=True)
    step: float = Field(gt=0, allow_inf_nan=False, strict=True)
    default: float = Field(allow_inf_nan=False, strict=True)

    @model_validator(mode="after")
    def _range(self) -> "SimParameter":
        if not self.minimum < self.maximum or not self.minimum <= self.default <= self.maximum:
            raise ValueError("parameter needs an ordered range containing its default")
        if self.step > self.maximum - self.minimum:
            raise ValueError("parameter step exceeds its range")
        for value in (self.default, self.maximum):
            steps = (value - self.minimum) / self.step
            if not math.isfinite(steps) or not math.isclose(
                steps, round(steps), abs_tol=1e-7, rel_tol=0
            ):
                raise ValueError("default and maximum must lie on parameter steps")
        return self
