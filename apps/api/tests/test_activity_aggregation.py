"""Unit coverage for the activity aggregation — the pure fold from telemetry rows (events +
minute buckets) to streaks / week bars / heat / feed. Deterministic: the clock and timezone are
inputs, never read from the environment."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from lunaris_api.activity import LearningEvent, derive_activity

# A Wednesday, mid-afternoon UTC — far from midnight so naive expectations stay readable.
NOW = datetime(2026, 7, 8, 15, 0, tzinfo=UTC)  # 2026-07-08 is a Wednesday
TOKYO = ZoneInfo("Asia/Tokyo")


def _minute(days_ago: int, hour: int = 10, minute: int = 0) -> datetime:
    base = NOW - timedelta(days=days_ago)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _mastered(days_ago: int, kc_id: str, course_id: str = "course-1") -> LearningEvent:
    return LearningEvent(
        event_type="mastered",
        course_id=course_id,
        course_title="How HTTPS works",
        lesson_id=None,
        lesson_title=None,
        kc_id=kc_id,
        kc_label=kc_id.upper(),
        occurred_at=NOW - timedelta(days=days_ago),
    )


def _completed(days_ago: int, lesson_id: str = "m-1-l0") -> LearningEvent:
    return LearningEvent(
        event_type="completed",
        course_id="course-1",
        course_title="How HTTPS works",
        lesson_id=lesson_id,
        lesson_title="Lesson 1 · Fundamentals",
        kc_id=None,
        kc_label=None,
        occurred_at=NOW - timedelta(days=days_ago),
    )


def test_everything_zero_without_history() -> None:
    # Act
    snapshot = derive_activity([], [], tz=UTC, now=NOW)

    # Assert — honest zeros, but the calendar shapes are still real (14 heat days, 7 week days).
    assert snapshot.current_streak == 0
    assert snapshot.longest_streak == 0
    assert snapshot.minutes_this_week == 0
    assert snapshot.concepts_this_week == 0
    assert len(snapshot.heat) == 14
    assert all(day.minutes == 0 and not day.active for day in snapshot.heat)
    assert len(snapshot.week) == 7
    assert snapshot.feed == []


def test_current_streak_counts_consecutive_days_ending_today() -> None:
    # Arrange — studied today, yesterday, and two days ago; nothing before.
    minutes = [_minute(0), _minute(1), _minute(2)]

    # Act
    snapshot = derive_activity([], minutes, tz=UTC, now=NOW)

    # Assert
    assert snapshot.current_streak == 3
    assert snapshot.longest_streak == 3


def test_streak_survives_an_inactive_today() -> None:
    # Arrange — studied yesterday and the day before, not (yet) today: the streak must not
    # read 0 in the morning.
    minutes = [_minute(1), _minute(2)]

    # Act
    snapshot = derive_activity([], minutes, tz=UTC, now=NOW)

    # Assert
    assert snapshot.current_streak == 2


def test_a_gap_breaks_the_current_streak_but_not_the_longest() -> None:
    # Arrange — a 5-day run long ago, then a gap, then just today.
    old_run = [_minute(days_ago) for days_ago in range(10, 15)]
    minutes = [*old_run, _minute(0)]

    # Act
    snapshot = derive_activity([], minutes, tz=UTC, now=NOW)

    # Assert
    assert snapshot.current_streak == 1
    assert snapshot.longest_streak == 5


def test_event_only_days_count_as_active() -> None:
    # Arrange — a mark yesterday but no recorded study minutes.
    events = [_completed(1)]

    # Act
    snapshot = derive_activity(events, [], tz=UTC, now=NOW)

    # Assert — the day is active for streak/heat purposes even at zero minutes.
    assert snapshot.current_streak == 1
    yesterday = [day for day in snapshot.heat if day.date == (NOW - timedelta(days=1)).date()]
    assert yesterday[0].active is True
    assert yesterday[0].minutes == 0


def test_week_starts_monday_and_sums_minutes_per_day() -> None:
    # Arrange — NOW is Wednesday: Monday=2 days ago (2 minutes), Tuesday=1 (1), Wednesday=0 (3).
    minutes = [
        _minute(2, hour=9, minute=0),
        _minute(2, hour=9, minute=1),
        _minute(1, hour=9, minute=0),
        _minute(0, hour=9, minute=0),
        _minute(0, hour=9, minute=1),
        _minute(0, hour=9, minute=2),
        # Last week's Sunday — inside the 14-day heat but outside this week's bars.
        _minute(3, hour=9, minute=0),
    ]

    # Act
    snapshot = derive_activity([], minutes, tz=UTC, now=NOW)

    # Assert
    assert [day.minutes for day in snapshot.week] == [2, 1, 3, 0, 0, 0, 0]
    assert snapshot.week[0].date.weekday() == 0  # Monday first
    assert snapshot.minutes_this_week == 6


def test_days_are_user_local_not_utc() -> None:
    # Arrange — a 23:30 UTC bucket belongs to the NEXT calendar day in Tokyo (+9). NOW itself
    # (15:00 UTC Wednesday) is already Thursday in Tokyo.
    late_utc = (NOW - timedelta(days=1)).replace(hour=23, minute=30)

    # Act
    snapshot = derive_activity([], [late_utc], tz=TOKYO, now=NOW)

    # Assert — the bucket (UTC July 7) lands on Tokyo's July 8: the viewer's YESTERDAY, so the
    # streak reads 1. Folded in UTC instead it would sit two days back and the streak would be 0.
    yesterday_tokyo = NOW.astimezone(TOKYO).date() - timedelta(days=1)
    active = [day for day in snapshot.heat if day.active]
    assert [day.date for day in active] == [yesterday_tokyo]
    assert snapshot.current_streak == 1


def test_concepts_this_week_counts_distinct_kcs() -> None:
    # Arrange — the same KC mastered twice this week (toggle-flap), another once, and one
    # mastered last week.
    events = [
        _mastered(0, "kc-a"),
        _mastered(1, "kc-a"),
        _mastered(1, "kc-b"),
        _mastered(8, "kc-old"),
    ]

    # Act
    snapshot = derive_activity(events, [], tz=UTC, now=NOW)

    # Assert — distinct within the current week only.
    assert snapshot.concepts_this_week == 2


def test_heat_covers_exactly_the_last_14_days_oldest_first() -> None:
    # Arrange — activity 13 days ago (the window's oldest day) and 14 days ago (outside).
    minutes = [_minute(13), _minute(14)]

    # Act
    snapshot = derive_activity([], minutes, tz=UTC, now=NOW)

    # Assert
    assert len(snapshot.heat) == 14
    assert snapshot.heat[0].date == (NOW - timedelta(days=13)).date()
    assert snapshot.heat[-1].date == NOW.date()
    assert snapshot.heat[0].active is True
    assert sum(1 for day in snapshot.heat if day.active) == 1


def test_feed_caps_at_fifty_recent_events() -> None:
    # Arrange — 60 completions today plus one 31 days ago (newest-first, as the store returns).
    events = [_completed(0, lesson_id=f"m-1-l{i}") for i in range(60)]
    events.append(_completed(31))

    # Act
    snapshot = derive_activity(events, [], tz=UTC, now=NOW)

    # Assert — capped at 50, and the 31-day-old event is outside the feed window regardless.
    assert len(snapshot.feed) == 50
    assert all(event.occurred_at >= NOW - timedelta(days=30) for event in snapshot.feed)
