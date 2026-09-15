from typing import Literal

from pydantic import Field

from ...schemas.base import CorpusModel
from .clip import VideoClip


class VideoGap(CorpusModel):
    job_id: str | None = None
    reason: Literal[
        "silent",
        "cue_too_long",
        "chapter_mismatch",
        "no_ready_video",
        "stale",
        "degraded",
        "malformed_timing",
        "unavailable",
        "media_unverified",
        "inventory_limit",
    ]


class VideoInventory(CorpusModel):
    clips: tuple[VideoClip, ...] = Field(default=(), max_length=5000)
    gaps: tuple[VideoGap, ...] = Field(default=(), max_length=1000)
