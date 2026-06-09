"""Unit tests for the keyless-build throttle's reservation logic (keyless-fallbacks T6).

The HTTP-level behaviour is covered by test_draft_throttle_api; these pin the throttle's own
contract deterministically — the per-day reset (via an injected clock, no real time), slot release,
per-tenant isolation, and the safety clamp — which the API path can't exercise cheaply.
"""

from datetime import UTC, datetime

import pytest
from lunaris_api.draft_throttle import (
    DraftBuildBusyError,
    DraftDailyCapReachedError,
    DraftTierDisabledError,
    KeylessBuildThrottle,
)


class _Clock:
    """A settable clock so a test can advance the day without waiting."""

    def __init__(self, day: int) -> None:
        self._day = day

    def set_day(self, day: int) -> None:
        self._day = day

    def __call__(self) -> datetime:
        return datetime(2026, 6, self._day, 12, 0, tzinfo=UTC)


def test_a_disabled_tier_refuses_every_reservation() -> None:
    throttle = KeylessBuildThrottle(enabled=False, daily_cap=10, max_concurrent=1)

    with pytest.raises(DraftTierDisabledError):
        throttle.reserve("user-a")


def test_releasing_a_slot_lets_the_next_build_in() -> None:
    # max_concurrent=1: the second reserve fails while the first is held, then passes once released.
    throttle = KeylessBuildThrottle(enabled=True, daily_cap=10, max_concurrent=1)

    held = throttle.reserve("user-a")
    with pytest.raises(DraftBuildBusyError):
        throttle.reserve("user-a")
    throttle.release(held)
    throttle.reserve("user-a")  # the freed slot admits the next build


def test_the_per_day_cap_counts_completed_builds() -> None:
    # A released (completed) build still counts: the daily allowance is consumed even after release.
    throttle = KeylessBuildThrottle(enabled=True, daily_cap=2, max_concurrent=1)

    throttle.release(throttle.reserve("user-a"))
    throttle.release(throttle.reserve("user-a"))
    with pytest.raises(DraftDailyCapReachedError):
        throttle.reserve("user-a")


def test_the_cap_resets_on_a_new_day() -> None:
    # Yesterday's builds don't count today — the cap is per calendar day.
    clock = _Clock(day=1)
    throttle = KeylessBuildThrottle(enabled=True, daily_cap=1, max_concurrent=1, clock=clock)

    throttle.release(throttle.reserve("user-a"))
    with pytest.raises(DraftDailyCapReachedError):
        throttle.reserve("user-a")
    clock.set_day(2)
    throttle.reserve("user-a")  # a fresh day's allowance


def test_the_per_day_cap_is_isolated_per_tenant() -> None:
    # One tenant exhausting their cap does not block another tenant.
    throttle = KeylessBuildThrottle(enabled=True, daily_cap=1, max_concurrent=2)

    throttle.reserve("user-a")
    with pytest.raises(DraftDailyCapReachedError):
        throttle.reserve("user-a")
    throttle.reserve("user-b")  # user-b has their own allowance


def test_a_zero_concurrency_setting_is_clamped_to_one() -> None:
    # A 0 would refuse every build silently; the operator disables the tier with the flag instead.
    throttle = KeylessBuildThrottle(enabled=True, daily_cap=10, max_concurrent=0)

    throttle.reserve("user-a")  # clamped to one slot, so one build is admitted
