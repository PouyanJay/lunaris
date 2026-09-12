import math
from typing import Literal

from pydantic import Field, model_validator

from ...graph.schema.base import LiveModel
from .parameter import SimParameter


class SimContract(LiveModel):
    """The teaching objective and controls shared by builder, verifier, tutor and iframe."""

    version: Literal[1] = 1
    objective: str = Field(min_length=1, max_length=1000)
    parameters: dict[str, SimParameter] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _names(self) -> "SimContract":
        if any(not key.isidentifier() or len(key) > 40 for key in self.parameters):
            raise ValueError("parameter names must be short identifiers")
        return self

    def validate_state(self, state: dict[str, float]) -> None:
        """Validate a complete snapshot before exposing it to a tutor or applying its command."""
        if state.keys() != self.parameters.keys():
            raise ValueError("state must name exactly the declared parameters")
        for name, parameter in self.parameters.items():
            value = state[name]
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError("state values must be finite numbers")
            if not parameter.minimum <= value <= parameter.maximum:
                raise ValueError("state value is outside its parameter range")
            steps = (value - parameter.minimum) / parameter.step
            if not math.isfinite(steps) or not math.isclose(
                steps, round(steps), abs_tol=1e-7, rel_tol=0
            ):
                raise ValueError("state value is not on a parameter step")

    def initial_state(self) -> dict[str, float]:
        return {name: parameter.default for name, parameter in self.parameters.items()}
