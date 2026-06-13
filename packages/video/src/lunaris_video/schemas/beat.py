from typing import Self

from pydantic import Field, model_validator

from lunaris_video.schemas.base import ContractModel


class Beat(ContractModel):
    """One beat of a scene: a visual action and the exact narration spoken during it.

    Beats are the sync unit — narration-driven timing (V3) and the WPM estimate (V1) both
    resolve durations per beat. A silent beat (``narration == ""``) is legitimate pacing, but it
    must carry an explicit ``min_visual_s``: with no words to time, the floor is the ONLY
    duration source, so its absence would make the beat unrenderable.
    """

    id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    narration: str
    min_visual_s: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _silent_beats_need_a_visual_floor(self) -> Self:
        if not self.narration and self.min_visual_s is None:
            raise ValueError("a silent beat (empty narration) requires an explicit min_visual_s")
        return self
