from pydantic import Field

from .base import CourseModel
from .enums import VideoKind

# Two schemas in one file by the tightly-coupled-sibling exception: DegradedScene only ever appears
# inside a VideoProvenance, and the two are never used apart.


class DegradedScene(CourseModel):
    """A scene Gate B could not fully clear, shipped anyway as the best-effort render.

    When a scene's visual defects survive the repair budget (or a repair breaks the render), the
    pipeline degrades to best-effort rather than failing the whole video — it keeps the
    least-defective renderable scene and records the unresolved ``issues`` here, so the artifact's
    provenance is honest about what is imperfect instead of presenting a degraded scene as clean.
    """

    scene_id: str
    issues: list[str] = Field(min_length=1)


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
    # Scenes shipped as best-effort because Gate B could not clear them (the 'publish anyway'
    # degrade). Empty for a video where every scene passed QA cleanly — and absent from older
    # artifact.json, which still loads (default + populate_by_name).
    degraded_scenes: list[DegradedScene] = Field(default_factory=list)
