from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# The state vocabulary is intrinsic to the mark (kept in lockstep with the DB CHECK), so the
# literal shares the entity's module.
LessonState = Literal["in_progress", "done"]


@dataclass(frozen=True)
class LessonMark:
    """A lesson's learner state — ``in_progress`` on first open, ``done`` on completion."""

    course_id: str
    lesson_id: str
    state: LessonState
    updated_at: datetime
