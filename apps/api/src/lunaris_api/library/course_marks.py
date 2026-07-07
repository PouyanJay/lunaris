from dataclasses import dataclass, field

from ..progress import CourseStateMark, LessonMark, ObjectiveMark


@dataclass(frozen=True)
class CourseMarks:
    """One course's slice of the learner's progress: its marks plus the open-recency state row
    (None until the course is first opened)."""

    objectives: list[ObjectiveMark] = field(default_factory=list)
    lessons: list[LessonMark] = field(default_factory=list)
    state: CourseStateMark | None = None
