from dataclasses import dataclass

from lunaris_runtime.schema import Course, CourseRun


@dataclass(frozen=True)
class LibraryEntry:
    """One library row's raw material: the operational run paired with its persisted course."""

    run: CourseRun
    course: Course
