from dataclasses import dataclass

from lunaris_video.models.video_outline import VideoOutline


@dataclass(frozen=True)
class PreparedVideoEvidence:
    job_id: str
    media_path: str
    title: str
    outline: VideoOutline
    artifact_bytes: tuple[bytes, bytes, bytes]
