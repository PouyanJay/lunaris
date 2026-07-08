from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from .learning_event import LearningEvent

_HEAT_DAYS = 14
_FEED_LIMIT = 50
_FEED_WINDOW = timedelta(days=30)


# The three value types exist only as derive_activity's return shape — tightly coupled, so they
# share its module (the rollups.py precedent for value types owned by their single producer).
@dataclass(frozen=True)
class HeatDay:
    """One of the last-14-days squares. ``active`` covers event-only days — a day with marks but
    no recorded study minutes still counts as studied."""

    date: date
    minutes: int
    active: bool


@dataclass(frozen=True)
class WeekDay:
    """One bar of the current ISO week (Monday-first)."""

    date: date
    minutes: int


@dataclass(frozen=True)
class ActivitySnapshot:
    """The derived activity rollup — recomputed per read from real rows, never stored."""

    current_streak: int
    longest_streak: int
    minutes_this_week: int
    concepts_this_week: int
    heat: list[HeatDay]
    week: list[WeekDay]
    feed: list[LearningEvent]


def _streak_ending_at(active_days: set[date], today: date) -> int:
    """Consecutive active days ending today — or ending yesterday when today is (so far)
    inactive, so the streak doesn't read 0 in the morning."""
    anchor = today if today in active_days else today - timedelta(days=1)
    length = 0
    while anchor in active_days:
        length += 1
        anchor -= timedelta(days=1)
    return length


def _longest_run(active_days: set[date]) -> int:
    longest = 0
    run = 0
    previous: date | None = None
    for day in sorted(active_days):
        run = run + 1 if previous == day - timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    return longest


def _week_bars(today: date, minutes_per_day: Counter) -> list[WeekDay]:
    """The ISO week (Monday-first) containing today, one bar per day."""
    monday = today - timedelta(days=today.weekday())
    return [
        WeekDay(date=day, minutes=minutes_per_day.get(day, 0))
        for day in (monday + timedelta(days=offset) for offset in range(7))
    ]


def _concepts_mastered(events: list[LearningEvent], days: set[date], tz: tzinfo) -> int:
    """Distinct (course, KC) pairs with a ``mastered`` event on one of ``days``."""
    return len(
        {
            (event.course_id, event.kc_id)
            for event in events
            if event.event_type == "mastered" and event.occurred_at.astimezone(tz).date() in days
        }
    )


def _heat_days(today: date, minutes_per_day: Counter, active_days: set[date]) -> list[HeatDay]:
    """The last 14 days, oldest first."""
    return [
        HeatDay(date=day, minutes=minutes_per_day.get(day, 0), active=day in active_days)
        for day in (today - timedelta(days=offset) for offset in range(_HEAT_DAYS - 1, -1, -1))
    ]


def derive_activity(
    events: list[LearningEvent],
    minutes: list[datetime],
    *,
    tz: tzinfo,
    now: datetime,
) -> ActivitySnapshot:
    """Fold telemetry rows into the Activity surface: streaks, week bars, 14-day heat, feed.

    Pure and deterministic — the clock and the viewer's timezone are (keyword-only) inputs. All
    day boundaries are user-local (``tz``): a 23:30 UTC study minute belongs to tomorrow in
    Tokyo. A day is "active" when it has a study-minute bucket OR any learning event. The feed
    is the newest ``50`` events within 30 days — grouping into Today/Yesterday labels is the
    client's job (it knows the viewer's locale).
    """
    today = now.astimezone(tz).date()
    minutes_per_day = Counter(bucket.astimezone(tz).date() for bucket in minutes)
    event_days = {event.occurred_at.astimezone(tz).date() for event in events}
    active_days = set(minutes_per_day) | event_days

    week = _week_bars(today, minutes_per_day)
    cutoff = now - _FEED_WINDOW
    # Sorted here, not trusted: both stores return newest-first today, but a pure fold must not
    # depend on an undocumented caller precondition for "the newest 50".
    recent = sorted(
        (event for event in events if event.occurred_at >= cutoff),
        key=lambda event: event.occurred_at,
        reverse=True,
    )

    return ActivitySnapshot(
        current_streak=_streak_ending_at(active_days, today),
        longest_streak=_longest_run(active_days),
        minutes_this_week=sum(entry.minutes for entry in week),
        concepts_this_week=_concepts_mastered(events, {entry.date for entry in week}, tz),
        heat=_heat_days(today, minutes_per_day, active_days),
        week=week,
        feed=recent[:_FEED_LIMIT],
    )
