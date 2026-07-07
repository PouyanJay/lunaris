from dataclasses import dataclass

from lunaris_runtime.schema import Course

from .store_protocol import LessonMark, ObjectiveMark


@dataclass(frozen=True)
class ProgressSummary:
    """The derived course-level rollup: counts plus a lesson-based completion percent."""

    understood_count: int
    objective_total: int
    lessons_done: int
    lesson_total: int
    percent: int


def derive_rollups(
    course: Course,
    objectives: list[ObjectiveMark],
    lessons: list[LessonMark],
) -> tuple[ProgressSummary, dict[str, bool]]:
    """Compute the summary + per-KC mastery from the course payload and the learner's marks.

    Nothing is stored: rollups are recomputed per read so a course rebuild (which can change
    module/objective shapes) can never leave a stale aggregate behind. A KC is mastered when
    EVERY objective that teaches it is understood; percent is lessons-done over lessons-total
    (the design's "x of y lessons · z%" reading).
    """
    understood = {(mark.module_id, mark.objective_index) for mark in objectives}
    done_lessons = {mark.lesson_id for mark in lessons if mark.state == "done"}

    objective_total = 0
    understood_count = 0
    lesson_total = 0
    lessons_done = 0
    kc_mastery: dict[str, bool] = {}
    for module in course.modules:
        for index, objective in enumerate(module.objectives):
            objective_total += 1
            is_understood = (module.id, index) in understood
            if is_understood:
                understood_count += 1
            if objective.kc:
                kc_mastery[objective.kc] = kc_mastery.get(objective.kc, True) and is_understood
        for lesson in module.lessons:
            lesson_total += 1
            if lesson.id in done_lessons:
                lessons_done += 1

    percent = round(100 * lessons_done / lesson_total) if lesson_total else 0
    summary = ProgressSummary(
        understood_count=understood_count,
        objective_total=objective_total,
        lessons_done=lessons_done,
        lesson_total=lesson_total,
        percent=percent,
    )
    return summary, kc_mastery
