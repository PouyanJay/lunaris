from typing import Self

from pydantic import Field, model_validator

from .base import CorpusModel
from .citation import CorpusCitation
from .provenance import CorpusProvenance
from .section import CorpusSection


class CorpusSnapshot(CorpusModel):
    schema_version: str = Field(default="1", min_length=1, max_length=30)
    caveats: tuple[str, ...] = Field(default=(), max_length=100)
    citations: tuple[CorpusCitation, ...] = Field(default=(), max_length=1000)
    source: CorpusProvenance
    sections: tuple[CorpusSection, ...] = Field(default=(), max_length=1000)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if len({section.locator for section in self.sections}) != len(self.sections):
            raise ValueError("Source locators must be unique")
        text_size = sum(
            len(s.text)
            + len(s.answer_key or "")
            + sum(len(c.text) for c in s.claims)
            + sum(len(o) for o in s.objectives)
            for s in self.sections
        )
        text_size += sum(len(c.model_dump_json()) for c in self.citations)
        text_size += sum(len(c) for c in self.caveats)
        if text_size > 200000:
            raise ValueError("Course material exceeds the source budget")
        if any(len(c) > 20000 for c in self.caveats):
            raise ValueError("Course caveat exceeds the source budget")
        if any(len(o) > 20000 for s in self.sections for o in s.objectives):
            raise ValueError("Course objective exceeds the source budget")
        if len({c.id for c in self.citations}) != len(self.citations):
            raise ValueError("Course citation identifiers must be unique")
        return self
