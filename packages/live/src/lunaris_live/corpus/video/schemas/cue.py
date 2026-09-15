from typing import Self

from pydantic import Field, model_validator

from ...schemas.base import CorpusModel


class Cue(CorpusModel):
    """One original spoken cue, in absolute source-video seconds."""

    start_s: float = Field(ge=0, allow_inf_nan=False)
    end_s: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_s <= self.start_s or not self.text.strip():
            raise ValueError("cue must have an ordered interval and spoken text")
        return self
