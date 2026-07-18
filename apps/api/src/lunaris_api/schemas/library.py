from datetime import datetime

from lunaris_runtime.schema import CourseStatus, CoverArtifact

from ..library import CourseLevel, LearnerCourseStatus
from .base import CamelModel


class CourseSummaryView(CamelModel):
    """One My-courses library card on the wire (camelCase). ``id`` is the course id the card
    opens; ``topic`` names the course, same word as ``Course``/``CourseRun``. ``level`` is null
    for a graphless course (no invented pill); ``built_at`` is the run's finish time — the sort
    key when the course has never been opened (``last_opened_at`` null). ``cover`` is the AI cover
    handle (or null) — kept for the reader's regenerate + full-size lightbox, which exchange the
    ``job_id`` for a fresh signed URL. ``thumb_url`` (+ its dual-theme ``thumb_url_light`` twin) is
    the display-size cover already signed at list time, so the grid renders cover-ready in ONE
    request instead of a per-card signed-URL exchange; both are null when there is nothing to sign
    (no cover, a non-READY cover, or storage that can't resize) and the card shows the Typographic
    cover."""

    id: str
    topic: str
    lesson_total: int
    lessons_done: int
    percent: int
    concept_total: int
    level: CourseLevel | None
    learner_status: LearnerCourseStatus
    course_status: CourseStatus
    built_at: datetime
    last_opened_at: datetime | None
    cover: CoverArtifact | None = None
    thumb_url: str | None = None
    thumb_url_light: str | None = None
