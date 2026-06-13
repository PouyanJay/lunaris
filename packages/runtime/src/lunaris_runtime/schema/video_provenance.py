from pydantic import Field

from .base import CourseModel
from .enums import VideoKind


class VideoProvenance(CourseModel):
    """Where a generated video came from — provenance is structural (CLAUDE.md contract).

    Built at the source (the pipeline, once the contract is planned and the factual gate has
    passed) and carried untouched through worker → storage → API. ``claim_ids`` are the verified
    claims the video's scenes cite — the grounding it asserts; ``contract_hash`` and ``input_hash``
    fingerprint what produced it; ``model`` and ``generated_at`` say who and when. An integration
    test asserts these are populated, not just that an MP4 exists.
    """

    job_id: str
    course_id: str
    lesson_id: str | None = None
    kind: VideoKind
    model: str
    contract_hash: str
    input_hash: str
    claim_ids: list[str] = Field(default_factory=list)
    # ISO-8601 instant, stamped when the pipeline produced the artifact — a string to match the
    # sibling provenance timestamp Citation.fetched_at (the established convention).
    generated_at: str
