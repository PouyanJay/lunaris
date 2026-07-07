from enum import StrEnum


class CourseLevel(StrEnum):
    """The library's level pill, bucketed from the graph's mean KC difficulty (real build data —
    the course payload persists no explicit level)."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
