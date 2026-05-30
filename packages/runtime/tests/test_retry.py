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
