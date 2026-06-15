from pydantic import Field

from .base import CourseModel
from .enums import VideoKind

# Two schemas in one file by the tightly-coupled-sibling exception: DegradedScene only ever appears
# inside a VideoProvenance, and the two are never used apart.


class DegradedScene(CourseModel):
    """A scene a gate could not fully clear, shipped anyway as the best-effort render.

    Two degrade sources merge here: Gate B's visual defects (spatial defects that survived the
    repair budget, or where a repair broke the render), and Gate D / Gate 1's sync imperfections (a
    beat that wouldn't sync, or a scene whose render drifted from its audio timeline). In every case
    the pipeline ships rather than failing the video or dropping narration — the unresolved
    ``issues`` are recorded here so the artifact's provenance is honest about what is imperfect
    instead of presenting a degraded scene as clean.
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
    # Scenes shipped as best-effort because a gate could not clear them (the 'publish anyway'
    # degrade): Gate B's spatial defects AND Gate D / Gate 1's sync imperfections. Empty for a video
    # where every gate passed cleanly — and absent from older artifact.json, which still loads
    # (default + populate_by_name).
    degraded_scenes: list[DegradedScene] = Field(default_factory=list)
    # DEPRECATED (always False). The pipeline no longer drops narration for a desync — an unsyncable
    # scene now ships voiced best-effort with the imperfection recorded in ``degraded_scenes``
    # (the product requires every course to carry narration). Retained only so pre-always-voiced
    # artifact.json (which may carry this key) still parses under the schema's extra="forbid".
    narration_dropped_for_desync: bool = False
