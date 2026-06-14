from .base import CourseModel
from .enums import VideoJobStatus, VideoKind
from .video_provenance import VideoProvenance


class VideoArtifact(CourseModel):
    """A finished video as it rides in the course payload (plan §1.3).

    Its defining payload is the grounding ``provenance`` — the video can only assert what the
    verified claims prove, and this records exactly which. ``kind`` and ``status`` say what it is
    and whether it is ready; ``narrated``/``duration_s`` describe playback. Populated by the build
    in V4 (``Lesson.video`` / ``Course.videos``); defined now so provenance traverses pipeline →
    payload → API against a stable shape.

    ``provenance`` is ``None`` for a video that has none — a FAILED job carries a retry-state
    artifact that may never have planned a contract (V4-T1). A READY artifact always carries it
    (provenance is built at the source the moment the contract is planned and Gate C passes).
    """

    kind: VideoKind
    status: VideoJobStatus
    provenance: VideoProvenance | None = None
    narrated: bool = False
    duration_s: float | None = None
