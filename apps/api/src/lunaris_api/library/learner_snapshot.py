from dataclasses import dataclass, field

from ..progress import CourseStateMark, LessonMark, ObjectiveMark


@dataclass(frozen=True)
class LearnerSnapshot:
    """The caller's whole-account progress — every mark and course-state row across courses.
    The library groups it per course; reading it once keeps the list endpoint at a fixed number
    of store queries regardless of course count."""

    objectives: list[ObjectiveMark] = field(default_factory=list)
    lessons: list[LessonMark] = field(default_factory=list)
    states: list[CourseStateMark] = field(default_factory=list)
