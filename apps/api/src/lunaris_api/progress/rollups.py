from dataclasses import dataclass

from lunaris_runtime.schema import Course

from .lesson_mark import LessonMark
from .objective_mark import ObjectiveMark


# ProgressSummary exists only as derive_rollups's return shape — tightly coupled, so they share
# a module (the cost.py precedent for a value type owned by its single producer).
@dataclass(frozen=True)
class ProgressSummary:
    """The derived course-level rollup: counts plus a lesson-based completion percent."""

    understood_count: int
    objective_total: int
    lessons_done: int
    lesson_total: int
    percent: int


def _objective_rollup(
    course: Course, understood: set[tuple[str, int]]
) -> tuple[int, int, dict[str, bool]]:
    """Count objectives (total, understood) and fold per-KC mastery — a KC is mastered when
    EVERY objective that teaches it is understood."""
    total = 0
    understood_count = 0
    kc_mastery: dict[str, bool] = {}
    for module in course.modules:
        for index, objective in enumerate(module.objectives):
            total += 1
            is_understood = (module.id, index) in understood
            if is_understood:
                understood_count += 1
            if objective.kc:
                kc_mastery[objective.kc] = kc_mastery.get(objective.kc, True) and is_understood
    return total, understood_count, kc_mastery


def _lesson_rollup(course: Course, done_lessons: set[str]) -> tuple[int, int]:
    """Count lessons (total, done) across the course's modules."""
    total = 0
    done = 0
    for module in course.modules:
        for lesson in module.lessons:
            total += 1
            if lesson.id in done_lessons:
                done += 1
    return total, done


def derive_rollups(
    course: Course,
    objectives: list[ObjectiveMark],
    lessons: list[LessonMark],
) -> tuple[ProgressSummary, dict[str, bool]]:
    """Compute the summary + per-KC mastery from the course payload and the learner's marks.

    Nothing is stored: rollups are recomputed per read so a course rebuild (which can change
    module/objective shapes) can never leave a stale aggregate behind. Percent is lessons-done
    over lessons-total (the design's "x of y lessons · z%" reading).
    """
    understood = {(mark.module_id, mark.objective_index) for mark in objectives}
    done_lessons = {mark.lesson_id for mark in lessons if mark.state == "done"}

    objective_total, understood_count, kc_mastery = _objective_rollup(course, understood)
    lesson_total, lessons_done = _lesson_rollup(course, done_lessons)

    percent = round(100 * lessons_done / lesson_total) if lesson_total else 0
    summary = ProgressSummary(
        understood_count=understood_count,
        objective_total=objective_total,
        lessons_done=lessons_done,
        lesson_total=lesson_total,
        percent=percent,
    )
    return summary, kc_mastery
