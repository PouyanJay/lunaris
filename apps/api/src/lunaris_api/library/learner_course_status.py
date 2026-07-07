from enum import StrEnum


class LearnerCourseStatus(StrEnum):
    """The learner-facing card status — where *this user* stands on a course. Distinct from the
    operational ``RunStatus`` (how the build went) and the pedagogical ``CourseStatus`` (whether
    the content passed its publish gates)."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
