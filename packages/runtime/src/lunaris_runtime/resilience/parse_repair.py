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

_logger = structlog.get_logger(__name__)

# Four attempts = one repair turn beyond the original generation, plus three retries: a parse that
# fails repeatedly (the dominant case is codegen "unterminated string literal") earns a fourth
# attempt before a hard build failure, at most one extra LLM call on the unlucky path. Symbolic
# callers (vision/sync QA, the planners) and their tests track this constant.
DEFAULT_PARSE_REPAIR_ATTEMPTS = 4


async def invoke_with_parse_repair[T](
    invoke: Callable[[str], Awaitable[str]],
    prompt: str,
    parse: Callable[[str], T],
    *,
    repair_instruction: str,
    max_attempts: int = DEFAULT_PARSE_REPAIR_ATTEMPTS,
    targeted_hint: Callable[[str], str | None] | None = None,
) -> T:
    """Run ``invoke`` → ``parse``, giving the model repair turns when the parse rejects.

    ``repair_instruction`` is a template with an ``{error}`` placeholder, appended to the
    original prompt on each repair turn (plain substitution, so the template may carry literal
    braces — e.g. a JSON example — unescaped). Only ``ValueError`` (the parsers' rejection
    type) triggers a repair; anything else propagates immediately.

    ``targeted_hint`` is an optional caller hook: given the parse-error string it returns extra,
    error-specific guidance to append AFTER the generic instruction, or ``None`` for the generic
    fallback. The primitive stays domain-agnostic — the caller owns the error→hint mapping (a JSON
    caller and a Python-codegen caller want different hints), so no domain knowledge leaks in here.
    """
    attempt_prompt = prompt
    for attempt in range(1, max_attempts + 1):
        content = await retry_on_rate_limit(lambda p=attempt_prompt: invoke(p))
        try:
            return parse(content)
        except ValueError as exc:
            if attempt == max_attempts:
                raise
            error = str(exc)
            _logger.warning(
                "llm_parse_repair", attempt=attempt, max_attempts=max_attempts, error=error
            )
            attempt_prompt = prompt + repair_instruction.replace("{error}", error)
            hint = targeted_hint(error) if targeted_hint is not None else None
            if hint:
                attempt_prompt += "\n" + hint
    raise AssertionError("unreachable")  # pragma: no cover
