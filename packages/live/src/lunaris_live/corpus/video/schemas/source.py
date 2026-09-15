from typing import Self

from pydantic import Field, model_validator

from ...schemas.base import CorpusModel
from .cue import Cue


class VideoChapter(CorpusModel):
    title: str = Field(min_length=1, max_length=300)
    start_s: float = Field(ge=0, allow_inf_nan=False)
    end_s: float = Field(gt=0, allow_inf_nan=False)


class VideoSource(CorpusModel):
    """Normalized measured media and existing transcript, with no playback credentials."""

    job_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=300)
    duration_s: float = Field(gt=0, le=14400, allow_inf_nan=False)
    chapters: tuple[VideoChapter, ...] = Field(default=(), max_length=500)
    transcript: tuple[Cue, ...] = Field(default=(), max_length=5000)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        for spans in (self.chapters, self.transcript):
            previous = 0.0
            for span in spans:
                if (
                    span.start_s < previous
                    or span.end_s <= span.start_s
                    or span.end_s > self.duration_s
                ):
                    raise ValueError("source timing must be ordered and within measured duration")
                previous = span.end_s
        return self
