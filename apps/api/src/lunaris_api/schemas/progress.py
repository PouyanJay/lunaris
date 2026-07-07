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


class ProgressSummaryView(CamelModel):
    """Derived course-level rollup — recomputed per read, never stored."""

    understood_count: int
    objective_total: int
    lessons_done: int
    lesson_total: int
    percent: int


class ProgressSnapshotView(CamelModel):
    """The caller's progress on one course: the raw marks plus rollups derived against the
    course payload. ``summary`` is null (and ``kc_mastery`` empty) when the course itself isn't
    loadable — progress rows are independent of the payload."""

    course_id: str
    objectives: list[ObjectiveProgressView]
    lessons: list[LessonProgressView]
    summary: ProgressSummaryView | None = None
    kc_mastery: dict[str, bool] = Field(default_factory=dict)


class ObjectiveMarkRequest(CamelModel):
    """Mark (or un-mark) one module objective as understood. Bounds mirror the DB checks."""

    module_id: str = Field(min_length=1, max_length=200)
    objective_index: int = Field(ge=0, le=999)
    understood: bool


class LessonMarkRequest(CamelModel):
    """Advance a lesson's learner state (idempotent upsert)."""

    lesson_id: str = Field(min_length=1, max_length=200)
    state: LessonState
