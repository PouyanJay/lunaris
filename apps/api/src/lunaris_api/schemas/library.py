from datetime import datetime

from lunaris_runtime.schema import CourseStatus, CoverArtifact

from ..library import CourseLevel, LearnerCourseStatus
from .base import CamelModel


class CourseSummaryView(CamelModel):
    """One My-courses library card on the wire (camelCase). ``id`` is the course id the card
    opens; ``topic`` names the course, same word as ``Course``/``CourseRun``. ``level`` is null
    for a graphless course (no invented pill); ``built_at`` is the run's finish time — the sort
    key when the course has never been opened (``last_opened_at`` null). ``cover`` is the AI cover
    handle (or null) — the card mints its signed URL on demand, else shows the Typographic cover."""

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
