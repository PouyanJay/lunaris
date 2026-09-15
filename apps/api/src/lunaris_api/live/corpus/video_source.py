import hashlib
import json

from lunaris_live.corpus.video.models.measured_media import MeasuredMedia
from lunaris_live.corpus.video.schemas.source import VideoSource

from .models.prepared_video_evidence import PreparedVideoEvidence


def measured_video_source(evidence: PreparedVideoEvidence, media: MeasuredMedia) -> VideoSource:
    """Bind the measured container and original evidence bytes to one normalized source."""
    digests = [media.digest, *(hashlib.sha256(raw).hexdigest() for raw in evidence.artifact_bytes)]
    identity = hashlib.sha256(json.dumps(digests, separators=(",", ":")).encode()).hexdigest()
    return VideoSource(
        job_id=evidence.job_id,
        source_digest=identity,
        title=evidence.title[:300],
        duration_s=media.duration_s,
        chapters=[
            {"title": chapter.title[:300], "start_s": chapter.start_s, "end_s": chapter.end_s}
            for chapter in evidence.outline.chapters
        ],
        transcript=[
            {"start_s": cue.start_s, "end_s": cue.end_s, "text": cue.text}
            for cue in evidence.outline.transcript
        ],
    )
