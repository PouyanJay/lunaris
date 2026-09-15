from dataclasses import dataclass

from ..schemas.clip import VideoClip


@dataclass(frozen=True)
class ClipVerificationRequest:
    course_id: str
    clip: VideoClip
    owner_id: str
    run_id: str
