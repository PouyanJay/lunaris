import asyncio
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
    max_attempts: int = 5,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run ``operation`` with exponential backoff on transient rate-limit errors.

    Re-raises immediately for non-rate-limit errors (auth, bad request) and after the
    final attempt. ``sleep`` is injectable so tests don't wait in real time.
    """
    delay = base_delay_s
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            if not _is_rate_limit(exc) or attempt == max_attempts:
                raise
            logger.warning("rate_limited_retrying", attempt=attempt, delay_s=delay)
            await sleep(delay)
            delay = min(delay * 2, max_delay_s)
    raise AssertionError("unreachable")  # pragma: no cover
