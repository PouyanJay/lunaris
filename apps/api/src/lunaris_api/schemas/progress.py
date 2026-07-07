from datetime import datetime

from pydantic import Field

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


class ObjectiveMarkRequest(CamelModel):
    """Mark (or un-mark) one module objective as understood. Bounds mirror the DB checks."""

    module_id: str = Field(min_length=1, max_length=200)
    objective_index: int = Field(ge=0, le=999)
    understood: bool


class LessonMarkRequest(CamelModel):
    """Advance a lesson's learner state (idempotent upsert)."""

    lesson_id: str = Field(min_length=1, max_length=200)
    state: LessonState
