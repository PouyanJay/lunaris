from datetime import date, datetime

from pydantic import Field

from ..activity import LearningEventType
from .base import CamelModel


class ActivityStatsView(CamelModel):
    """The four stat tiles — derived per read from real rows, never stored, never guessed."""

    current_streak: int
    longest_streak: int
    minutes_this_week: int
    concepts_this_week: int


class HeatDayView(CamelModel):
    """One of the last-14-days heat squares. ``active`` covers event-only days (a day with marks
    but no recorded study minutes still counts as studied)."""

    date: date
    minutes: int
    active: bool


class WeekDayView(CamelModel):
    """One bar of the current ISO week (Monday-first) study-minutes chart."""

    date: date
    minutes: int


class ActivityFeedItemView(CamelModel):
    """One feed row; day grouping and relative times are derived client-side (the client knows
    the viewer's locale/timezone)."""

    event_type: LearningEventType
    course_id: str
    course_title: str | None = None
    lesson_id: str | None = None
    lesson_title: str | None = None
    kc_id: str | None = None
    kc_label: str | None = None
    occurred_at: datetime


class ActivityView(CamelModel):
    """The learner's activity snapshot: stat tiles + 14-day heat + week bars + recent feed."""

    stats: ActivityStatsView
    heat: list[HeatDayView] = Field(default_factory=list)
    week: list[WeekDayView] = Field(default_factory=list)
    feed: list[ActivityFeedItemView] = Field(default_factory=list)
