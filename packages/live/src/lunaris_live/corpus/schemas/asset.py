from typing import Literal, Self

from pydantic import Field, model_validator

from ..video.schemas.clip import VideoClip
from .asset_verification import AssetVerification
from .base import CorpusModel


class NodeAsset(CorpusModel):
    """Public supporting-material reference, never assessment answers or signed URLs."""

    asset_id: str = Field(min_length=1, max_length=100)
    kind: Literal["lesson", "assessment", "video_clip"]
    origin: Literal["generated", "ingested"]
    locator: str = Field(min_length=1, max_length=300, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(default="", max_length=500)
    excerpt: str = Field(default="", max_length=8000)
    source_label: str = Field(default="", max_length=500)
    verification: AssetVerification | None = None
    clip: VideoClip | None = None

    @model_validator(mode="after")
    def validate_clip_binding(self) -> Self:
        if self.clip is not None and (
            self.kind != "video_clip" or self.locator != self.clip.locator
        ):
            raise ValueError("Video material must reference its exact clip evidence")
        if self.kind == "video_clip" and self.verification is not None and self.clip is None:
            raise ValueError("Verified video material requires clip evidence")
        return self
