from .base import CourseModel
from .enums import ReviewGateStatus


class ReviewGate(CourseModel):
    """One publish-gate verdict captured at finalize (course-review-publish).

    Finalize runs four gates — structure, coverage, grounding honesty, author confidence — then
    (before this feature) dropped their reasons, leaving ``review`` a terminal, unexplained state.
    Capturing them here lets the review drawer show the owner WHY a course is held, so approving is
    an informed decision. Persisted inside the course JSONB payload (no separate table); the list is
    empty on a course built before this feature.
    """

    # Stable gate key: ``structure`` | ``coverage`` | ``grounding`` | ``authoring``.
    key: str
    # Human label, e.g. "Structure".
    label: str
    status: ReviewGateStatus
    # One-sentence, learner-facing reason for the verdict (empty for a clean gate needs no words).
    detail: str = ""
