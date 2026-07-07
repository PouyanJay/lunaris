from collections import defaultdict

from ..progress import LessonMark, ObjectiveMark
from .course_summary import CourseSummary
from .derive_course_summary import derive_course_summary
from .library_entry import LibraryEntry


def assemble_course_summaries(
    entries: list[LibraryEntry],
    objectives: list[ObjectiveMark],
    lessons: list[LessonMark],
) -> list[CourseSummary]:
    """Fold the library entries + the caller's whole progress snapshot into card summaries,
    preserving entry order (the run index is newest-first). Marks are grouped by course here so
    the store is read once, not once per course."""
    objectives_by_course: dict[str, list[ObjectiveMark]] = defaultdict(list)
    for objective in objectives:
        objectives_by_course[objective.course_id].append(objective)
    lessons_by_course: dict[str, list[LessonMark]] = defaultdict(list)
    for lesson in lessons:
        lessons_by_course[lesson.course_id].append(lesson)
    return [
        derive_course_summary(
            entry,
            objectives_by_course.get(entry.course.id, []),
            lessons_by_course.get(entry.course.id, []),
        )
        for entry in entries
    ]
