from .base import CamelModel


class CourseSummaryView(CamelModel):
    """One My-courses library card on the wire (camelCase). ``id`` is the course id the card
    opens; ``topic`` names the course, same word as ``Course``/``CourseRun``."""

    id: str
    topic: str
    lesson_total: int
