from dataclasses import dataclass

from lunaris_runtime.schema import VideoKind


@dataclass(frozen=True)
class VideoSlot:
    owner_id: str
    kind: VideoKind
    lesson_id: str | None
