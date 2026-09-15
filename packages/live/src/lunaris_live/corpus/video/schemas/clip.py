from typing import Self

from pydantic import Field, model_validator

from ...schemas.base import CorpusModel
from .cue import Cue


class VideoClip(CorpusModel):
    """An evidence-aligned candidate; semantic verification is a separate mapping step."""

    job_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    locator: str = Field(pattern=r"^video:[a-zA-Z0-9_-]+:[a-f0-9]{64}:[0-9]+:[0-9]+$")
    start_s: float = Field(ge=0, allow_inf_nan=False)
    end_s: float = Field(gt=0, allow_inf_nan=False)
    duration_s: float = Field(gt=0, allow_inf_nan=False)
    title: str = Field(min_length=1, max_length=300)
    transcript: tuple[Cue, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def aligned(self) -> Self:
        if not 0 < self.end_s - self.start_s <= 90 or self.end_s > self.duration_s:
            raise ValueError("clip must be bounded to the source duration and 90 seconds")
        if self.transcript[0].start_s != self.start_s or self.transcript[-1].end_s != self.end_s:
            raise ValueError("clip edges must match original cues")
        previous = self.start_s
        for cue in self.transcript:
            if cue.start_s < previous or cue.end_s > self.end_s:
                raise ValueError("clip cues must be ordered within its bounds")
            previous = cue.end_s
        if not self.locator.startswith(f"video:{self.job_id}:{self.source_digest}:"):
            raise ValueError("clip locator must bind its source identity")
        return self
