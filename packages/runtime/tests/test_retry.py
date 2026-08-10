import pytest
from lunaris_runtime.resilience import retry_on_rate_limit, retry_on_transient


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


class _ConnectionBlipError(Exception):
    """What the Anthropic SDK raises when the socket dies mid-call: no status, no rate-limit
    wording, nothing the rate-limit predicate can recognise."""

    def __str__(self) -> str:
        return "Connection error."


async def test_a_connection_blip_is_not_a_rate_limit() -> None:
    """The default predicate stays exactly as narrow as it was — widening it under every existing
    caller is a behaviour change none of them asked for."""
    # Arrange
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        raise _ConnectionBlipError

    # Act / Assert
    with pytest.raises(_ConnectionBlipError):
        await retry_on_rate_limit(operation, base_delay_s=0, sleep=_noop_sleep)
    assert attempts == 1, "a connection error was retried by the rate-limit retry"


async def test_a_transient_retry_survives_a_connection_blip() -> None:
    """T9 found this the expensive way: five of ten real compiles died on ``APIConnectionError``.

    The call it kills is decomposition — the single serial call the compiler documents as the one
    failure it cannot degrade around — so one dropped socket costs the learner the whole three
    minutes, and D4 charges them a daily compile for it.
    """
    # Arrange
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _ConnectionBlipError
        return "recovered"

    # Act / Assert
    assert await retry_on_transient(operation, base_delay_s=0, sleep=_noop_sleep) == "recovered"
    assert attempts == 3


async def test_a_transient_retry_still_gives_up_on_a_real_error() -> None:
    """Retrying a bad request or a bad key just burns the budget slowly — the failure is ours and
    it will not heal."""
    # Arrange
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid_request_error: your prompt is malformed")

    # Act / Assert
    with pytest.raises(ValueError):
        await retry_on_transient(operation, base_delay_s=0, sleep=_noop_sleep)
    assert attempts == 1


class _RequestTimeoutError(Exception):
    """A request that never came back — the other half of "transient", and the one a compile
    running fifteen concurrent calls hits when the provider is slow rather than broken."""


async def test_a_transient_retry_survives_a_request_timeout() -> None:
    """Pinned separately from the connection blip: they are two different clauses of the predicate,
    and a test of one says nothing about the other."""
    # Arrange
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise _RequestTimeoutError("request timed out")
        return "recovered"

    # Act / Assert
    assert await retry_on_transient(operation, base_delay_s=0, sleep=_noop_sleep) == "recovered"
    assert attempts == 2
