from lunaris_runtime.schema import Course

from .course_summary import CourseSummary


def derive_course_summary(course: Course) -> CourseSummary:
    """Fold a persisted course payload into its library-card facts."""
    lesson_total = sum(len(module.lessons) for module in course.modules)
    return CourseSummary(course_id=course.id, topic=course.topic, lesson_total=lesson_total)
