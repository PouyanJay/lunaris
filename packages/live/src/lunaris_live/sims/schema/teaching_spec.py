from typing import Annotated

from pydantic import Field, model_validator

from ...graph.schema.base import LiveModel
from .contract import SimContract


class TeachingCase(LiveModel):
    """An independently authored state and the visible consequences it must produce."""

    state: dict[str, Annotated[float, Field(strict=True, allow_inf_nan=False)]]
    outputs: dict[str, str] = Field(min_length=1, max_length=8)


class TeachingSpec(LiveModel):
    contract: SimContract
    source: str = Field(min_length=1, max_length=1000)
    source_version: str = Field(min_length=1, max_length=100)
    cases: list[TeachingCase] = Field(min_length=3, max_length=12)

    @model_validator(mode="after")
    def valid_cases(self) -> "TeachingSpec":
        for case in self.cases:
            self.contract.validate_state(case.state)
            for key, value in case.outputs.items():
                if not key.isidentifier() or len(key) > 40 or len(value) > 200:
                    raise ValueError(
                        "Output names and expected text must be bounded identifiers/text."
                    )
        if len({tuple(sorted(case.state.items())) for case in self.cases}) < 3:
            raise ValueError("At least three distinct states are required.")
        return self
