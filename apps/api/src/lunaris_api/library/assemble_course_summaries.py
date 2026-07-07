from collections import defaultdict

from ..progress import LessonMark, ObjectiveMark
from .course_marks import CourseMarks
from .course_summary import CourseSummary
from .derive_course_summary import derive_course_summary
from .learner_snapshot import LearnerSnapshot
from .library_entry import LibraryEntry


def assemble_course_summaries(
    entries: list[LibraryEntry], snapshot: LearnerSnapshot
) -> list[CourseSummary]:
    """Fold the library entries + the caller's whole-account snapshot into card summaries,
    sorted by recency — last opened when the learner has opened the course, else its build time
    (so a brand-new build surfaces at the top until something else is opened). Marks are grouped
    by course here so the store is read once, not once per course."""
    objectives_by_course: dict[str, list[ObjectiveMark]] = defaultdict(list)
    for objective in snapshot.objectives:
        objectives_by_course[objective.course_id].append(objective)
    lessons_by_course: dict[str, list[LessonMark]] = defaultdict(list)
    for lesson in snapshot.lessons:
        lessons_by_course[lesson.course_id].append(lesson)
    state_by_course = {state.course_id: state for state in snapshot.states}
    summaries = [
        derive_course_summary(
            entry,
            CourseMarks(
                objectives=objectives_by_course.get(entry.course.id, []),
                lessons=lessons_by_course.get(entry.course.id, []),
                state=state_by_course.get(entry.course.id),
            ),
        )
        for entry in entries
    ]
    return sorted(
        summaries, key=lambda summary: summary.last_opened_at or summary.built_at, reverse=True
    )
