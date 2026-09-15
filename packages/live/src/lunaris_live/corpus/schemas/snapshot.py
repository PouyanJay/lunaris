from typing import Self

from pydantic import Field, model_validator

from .base import CorpusModel
from .provenance import CorpusProvenance
from .section import CorpusSection


class CorpusSnapshot(CorpusModel):
    source: CorpusProvenance
    sections: tuple[CorpusSection, ...] = Field(default=(), max_length=1000)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if len({section.locator for section in self.sections}) != len(self.sections):
            raise ValueError("Source locators must be unique")
        if sum(len(s.text) + len(s.answer_key or "") for s in self.sections) > 200000:
            raise ValueError("Course material exceeds the source budget")
        return self
