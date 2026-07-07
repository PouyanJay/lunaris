from dataclasses import dataclass


@dataclass(frozen=True)
class CourseSummary:
    """One My-courses library card's facts — derived per read, never stored (a rebuild can change
    the course shape, so a stored aggregate could go stale)."""

    course_id: str
    topic: str
    lesson_total: int
