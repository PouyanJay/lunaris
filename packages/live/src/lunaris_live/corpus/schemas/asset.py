from typing import Literal

from pydantic import Field

from .base import CorpusModel


class NodeAsset(CorpusModel):
    """Public supporting-material reference, never assessment answers or signed URLs."""

    asset_id: str = Field(min_length=1, max_length=100)
    kind: Literal["lesson", "assessment", "video_clip"]
    origin: Literal["generated", "ingested"]
    locator: str = Field(min_length=1, max_length=300, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
