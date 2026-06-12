"""Bounded parse-repair turns around a one-shot "model emits text → strict parse" call.

The build's structured outputs (lessons, curricula) are parsed strictly — the schemas make a
partial artifact unrepresentable — so a single incomplete or malformed generation would
otherwise fail an entire run at one step. This primitive re-prompts with the parse error
folded into the ORIGINAL prompt (never the prior repair prompt, so feedback can't stack
across attempts), up to a bounded number of turns, before re-raising the parse error
unwrapped. Rate-limit backoff wraps every attempt.
"""

from collections.abc import Awaitable, Callable

import structlog

from .retry import retry_on_rate_limit

logger = structlog.get_logger()

DEFAULT_PARSE_REPAIR_ATTEMPTS = 3


async def invoke_with_parse_repair[T](
    invoke: Callable[[str], Awaitable[str]],
    prompt: str,
    parse: Callable[[str], T],
    *,
    repair_instruction: str,
    max_attempts: int = DEFAULT_PARSE_REPAIR_ATTEMPTS,
) -> T:
    """Run ``invoke`` → ``parse``, giving the model repair turns when the parse rejects.

    ``repair_instruction`` is a template with an ``{error}`` placeholder, appended to the
    original prompt on each repair turn (plain substitution, so the template may carry literal
    braces — e.g. a JSON example — unescaped). Only ``ValueError`` (the parsers' rejection
    type) triggers a repair; anything else propagates immediately.
    """
    attempt_prompt = prompt
    for attempt in range(1, max_attempts + 1):
        content = await retry_on_rate_limit(lambda p=attempt_prompt: invoke(p))
        try:
            return parse(content)
        except ValueError as exc:
            if attempt == max_attempts:
                raise
            logger.warning(
                "llm_parse_repair", attempt=attempt, max_attempts=max_attempts, error=str(exc)
            )
            attempt_prompt = prompt + repair_instruction.replace("{error}", str(exc))
    raise AssertionError("unreachable")  # pragma: no cover
