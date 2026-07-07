from collections.abc import Sequence

from lunaris_runtime.schema import KnowledgeComponent

from ..progress import LessonMark, ObjectiveMark, derive_rollups
from .course_level import CourseLevel
from .course_summary import CourseSummary
from .learner_course_status import LearnerCourseStatus
from .library_entry import LibraryEntry

# Mean-difficulty cut points for the level pill: [0, 0.34) beginner, [0.34, 0.67) intermediate,
# [0.67, 1] advanced — thirds of the KC difficulty scale, boundaries inclusive upward.
_INTERMEDIATE_FLOOR = 0.34
_ADVANCED_FLOOR = 0.67


def _bucket_level(nodes: Sequence[KnowledgeComponent]) -> CourseLevel | None:
    if not nodes:
        return None  # a graphless course gets no pill — never an invented level
    mean = sum(node.difficulty for node in nodes) / len(nodes)
    if mean < _INTERMEDIATE_FLOOR:
        return CourseLevel.BEGINNER
    if mean < _ADVANCED_FLOOR:
        return CourseLevel.INTERMEDIATE
    return CourseLevel.ADVANCED


def _derive_learner_status(
    *, lessons_done: int, lesson_total: int, has_marks: bool
) -> LearnerCourseStatus:
    if lesson_total > 0 and lessons_done == lesson_total:
        return LearnerCourseStatus.COMPLETED
    if has_marks:
        return LearnerCourseStatus.IN_PROGRESS
    return LearnerCourseStatus.NOT_STARTED


def derive_course_summary(
    entry: LibraryEntry, objectives: list[ObjectiveMark], lessons: list[LessonMark]
) -> CourseSummary:
    """Fold one library entry + the caller's progress marks into its card facts.

    Rollups reuse the P2 derivation (lesson-based percent, recomputed per read). ``completed``
    requires every lesson done on a course that HAS lessons — a zero-lesson course with marks
    reads ``in_progress``, never a vacuous 0/0 completion.
    """
    summary, _ = derive_rollups(entry.course, objectives, lessons)
    nodes = entry.course.graph.nodes
    return CourseSummary(
        course_id=entry.course.id,
        topic=entry.course.topic,
        lesson_total=summary.lesson_total,
        lessons_done=summary.lessons_done,
        percent=summary.percent,
        concept_total=len(nodes),
        level=_bucket_level(nodes),
        learner_status=_derive_learner_status(
            lessons_done=summary.lessons_done,
            lesson_total=summary.lesson_total,
            has_marks=bool(objectives or lessons),
        ),
        course_status=entry.course.status,
        built_at=entry.run.updated_at,
    )
