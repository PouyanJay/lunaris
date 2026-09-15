from dataclasses import dataclass
from typing import Literal

from ...video.schemas.clip import VideoClip


@dataclass(frozen=True)
class MappingCandidate:
    locator: str
    kind: Literal["lesson", "assessment", "video_clip"]
    excerpt: str
    title: str
    clip: VideoClip | None = None
