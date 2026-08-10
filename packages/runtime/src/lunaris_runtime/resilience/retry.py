import asyncio
import random
from collections.abc import Awaitable, Callable

import structlog

logger = structlog.get_logger()


def _is_rate_limit(exc: BaseException) -> bool:
    """Detect a provider rate-limit / overload error without importing the SDK.

    Matches by class name + message so it works across anthropic/httpx versions and
    keeps this helper provider-agnostic.
    """
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "overloaded" in name:
        return True
    text = str(exc).lower()
    return "rate_limit" in text or "429" in text or "overloaded" in text


def _is_transient(exc: BaseException) -> bool:
    """Detect anything worth trying again — a rate limit, or the connection itself failing.

    Connection-level failures are matched the same way rate limits are: by class name and message,
    so this stays provider-agnostic and does not import an SDK. The provider's own client already
    retries a couple of times before surfacing one, so an error reaching here has already survived
    that — which is why the back-off above it is worth having rather than redundant.
    """
    if _is_rate_limit(exc):
        return True
    name = type(exc).__name__.lower()
    if "connection" in name or "timeout" in name:
        return True
    text = str(exc).lower()
    return "connection error" in text or "connection reset" in text


async def retry_on_transient[T](
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 8,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: Callable[[float, float], float] = random.uniform,
) -> T:
    """``retry_on_rate_limit``, widened to cover a dropped connection as well.

    A separate entry point rather than a widened default, because every existing caller chose the
    narrow behaviour and a connection error means something different to each of them. Live's graph
    compiler uses this one: its decomposition is a single serial call it explicitly cannot degrade
    around, so a dropped socket there costs a learner the whole three-minute compile — which T9's
    ten-topic eval demonstrated, five times in one run.
    """
    return await retry_on_rate_limit(
        operation,
        is_retryable=_is_transient,
        max_attempts=max_attempts,
        base_delay_s=base_delay_s,
        max_delay_s=max_delay_s,
        sleep=sleep,
        rng=rng,
    )


async def retry_on_rate_limit[T](
    operation: Callable[[], Awaitable[T]],
    *,
    is_retryable: Callable[[BaseException], bool] = _is_rate_limit,
    max_attempts: int = 8,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: Callable[[float, float], float] = random.uniform,
) -> T:
    """Run ``operation`` with full-jitter exponential backoff on transient rate-limit errors.

    The back-off uses *full jitter* (AWS-style): each wait is drawn uniformly from
    ``[0, cap]`` where ``cap`` grows exponentially (``base_delay_s * 2**(attempt-1)``,
    capped at ``max_delay_s``). Jitter is essential, not cosmetic: many calls fan out
    concurrently (e.g. the O(n²) pairwise prerequisite judgments), and without it they
    back off in lockstep — retrying in the same instant, colliding again, and exhausting
    their attempts against a fixed per-minute quota. Spreading retries across the window
    de-synchronises the herd so the burst drains within the provider's rate limit.

    Re-raises immediately for non-rate-limit errors (auth, bad request) and after the
    final attempt. ``sleep`` and ``rng`` are injectable so tests are deterministic and
    don't wait in real time.

    ``is_retryable`` decides what counts as transient. It defaults to rate limits alone — every
    caller that predates it chose exactly that — and ``retry_on_transient`` is the widened variant
    for callers whose single failed call costs more than a retry.
    """
    backoff_cap_s = base_delay_s
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            if not is_retryable(exc) or attempt == max_attempts:
                raise
            delay = rng(0.0, backoff_cap_s)
            logger.warning("rate_limited_retrying", attempt=attempt, delay_s=delay)
            await sleep(delay)
            backoff_cap_s = min(backoff_cap_s * 2, max_delay_s)
    raise AssertionError("unreachable")  # pragma: no cover
