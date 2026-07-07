from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CourseStateMark:
    """One (user, course) state row: when the course was last opened, and at which lesson.
    ``last_lesson_id`` is None when the learner only ever opened non-reader views."""

    course_id: str
    last_opened_at: datetime
    last_lesson_id: str | None
