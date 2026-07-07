from datetime import datetime

from ..progress import LessonState
from .base import CamelModel


class ObjectiveProgressView(CamelModel):
    """One understood objective, keyed by its module + position (objectives carry no id)."""

    module_id: str
    objective_index: int
    understood_at: datetime


class LessonProgressView(CamelModel):
    """A lesson's learner state: in_progress on first open, done on completion."""

    lesson_id: str
    state: LessonState
    updated_at: datetime


class ProgressSnapshotView(CamelModel):
    """The caller's progress on one course — the raw marks the reader and rollups derive from."""

    course_id: str
    objectives: list[ObjectiveProgressView]
    lessons: list[LessonProgressView]
