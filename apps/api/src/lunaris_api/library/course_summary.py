from dataclasses import dataclass
from datetime import datetime

from lunaris_runtime.schema import CourseStatus

from .course_level import CourseLevel
from .learner_course_status import LearnerCourseStatus


@dataclass(frozen=True)
class CourseSummary:
    """One My-courses library card's facts — derived per read, never stored (a rebuild can change
    the course shape, so a stored aggregate could go stale)."""

    course_id: str
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
