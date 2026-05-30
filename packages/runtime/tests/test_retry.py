import pytest
from lunaris_runtime.resilience import retry_on_rate_limit


class _RateLimitError(Exception):
    """Stands in for anthropic.RateLimitError (matched by name)."""


async def _noop_sleep(_seconds: float) -> None:
    return None


async def test_retries_then_succeeds_on_rate_limit() -> None:
    # Arrange — fails twice with a rate limit, then succeeds
    calls = {"n": 0}

    async def operation() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _RateLimitError("429 rate_limit_error")
        return "ok"

    # Act
    result = await retry_on_rate_limit(operation, base_delay_s=0, sleep=_noop_sleep)

    # Assert
    assert result == "ok"
    assert calls["n"] == 3


async def test_non_rate_limit_error_is_not_retried() -> None:
    # Arrange
    calls = {"n": 0}

    async def operation() -> str:
        calls["n"] += 1
        raise ValueError("bad request")

    # Act / Assert — propagates immediately, no retry
    with pytest.raises(ValueError, match="bad request"):
        await retry_on_rate_limit(operation, sleep=_noop_sleep)
    assert calls["n"] == 1


async def test_gives_up_after_max_attempts() -> None:
    # Arrange — always rate-limited
    calls = {"n": 0}

    async def operation() -> str:
        calls["n"] += 1
        raise _RateLimitError("overloaded")

    # Act / Assert
    with pytest.raises(_RateLimitError):
        await retry_on_rate_limit(operation, max_attempts=3, base_delay_s=0, sleep=_noop_sleep)
    assert calls["n"] == 3


async def test_full_jitter_samples_within_exponential_cap() -> None:
    # Arrange — always rate-limited; record every back-off sleep and the jitter window
    delays: list[float] = []
    windows: list[tuple[float, float]] = []

    async def operation() -> str:
        raise _RateLimitError("429 rate_limit_error")

    async def recording_sleep(seconds: float) -> None:
        delays.append(seconds)

    def rng_high(low: float, high: float) -> float:
        windows.append((low, high))
        return high  # sample the top of the full-jitter window so we can assert the cap

    # Act — 4 attempts → 3 back-off sleeps; cap doubles 1 → 2 → 4, capped at max_delay_s
    with pytest.raises(_RateLimitError):
        await retry_on_rate_limit(
            operation,
            max_attempts=4,
            base_delay_s=1.0,
            max_delay_s=30.0,
            sleep=recording_sleep,
            rng=rng_high,
        )

    # Assert — full jitter draws from [0, exponential_cap]; top-of-window equals the cap
    assert windows == [(0.0, 1.0), (0.0, 2.0), (0.0, 4.0)]
    assert delays == [1.0, 2.0, 4.0]


async def test_full_jitter_can_sample_zero_to_spread_the_herd() -> None:
    # Arrange — a low draw must be honoured so concurrent retries de-synchronise
    delays: list[float] = []

    async def operation() -> str:
        raise _RateLimitError("overloaded")

    async def recording_sleep(seconds: float) -> None:
        delays.append(seconds)

    def rng_low(low: float, _high: float) -> float:
        return low

    # Act
    with pytest.raises(_RateLimitError):
        await retry_on_rate_limit(
            operation, max_attempts=3, base_delay_s=1.0, sleep=recording_sleep, rng=rng_low
        )

    # Assert — bottom of the window is 0, so a herd does not retry in lockstep
    assert delays == [0.0, 0.0]
