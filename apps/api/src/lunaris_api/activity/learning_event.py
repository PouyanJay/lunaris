from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# The event vocabulary (kept in lockstep with the DB check): `started` / `completed` are lesson
# transitions, `mastered` is a knowledge component newly flipping mastered, `verified` is reserved
# for a future real reviewing action — nothing emits it today (honest-data rule).
LearningEventType = Literal["started", "completed", "mastered", "verified"]


@dataclass(frozen=True)
class LearningEvent:
    """One telemetry fact: something the learner did, when they did it.

    Titles are denormalized at write time so the feed renders without re-fetching courses and
    survives a course rebuild or deletion — an event is a historical record, not a live join.
    """

    event_type: LearningEventType
    course_id: str
    course_title: str | None
    lesson_id: str | None
    lesson_title: str | None
    kc_id: str | None
    kc_label: str | None
    occurred_at: datetime
