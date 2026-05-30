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


async def retry_on_rate_limit[T](
    operation: Callable[[], Awaitable[T]],
    *,
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
    """
    backoff_cap_s = base_delay_s
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            if not _is_rate_limit(exc) or attempt == max_attempts:
                raise
            delay = rng(0.0, backoff_cap_s)
            logger.warning("rate_limited_retrying", attempt=attempt, delay_s=delay)
            await sleep(delay)
            backoff_cap_s = min(backoff_cap_s * 2, max_delay_s)
    raise AssertionError("unreachable")  # pragma: no cover
