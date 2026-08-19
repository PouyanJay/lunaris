import asyncio
from collections.abc import Callable

from lunaris_runtime.resilience import build_chat_model, retry_on_transient

#: Matches the compiler's: three attempts inside a four-second ceiling survives a dropped socket
#: without eating any caller's own deadline. The library defaults (eight attempts, thirty seconds)
#: are sized for a batch job and would turn a fast clean failure into a slow cancelled one.
_TRANSIENT_ATTEMPTS = 3
_TRANSIENT_MAX_DELAY_S = 4.0


class ModelCallTimedOutError(RuntimeError):
    """The whole call, retries included, ran past the caller's deadline."""


class ModelCallFailedError(RuntimeError):
    """The provider refused, or answered with something that was not a message."""


async def ask_model(
    client: object | None,
    *,
    model_name: str,
    prompt: str,
    deadline_s: float,
    on_client: Callable[[object], None],
) -> str:
    """One bounded, retried, whole-answer call to a chat model, as text.

    The shape every non-streaming Live model call shares (the tutor's lesson, the grader, the
    interviewer, the prior mapper): build the client on first use so constructing the caller needs
    no key, wrap the *whole* call — retries included — in the caller's deadline so a learner cannot
    be left waiting because each attempt was inside its own budget, retry the transient failures,
    and hand back the words. It reports two failures, timed out and failed, and the caller names
    them in its own vocabulary (``TutorUnavailableError``, ``GraderUnavailableError`` …) — which is
    what a learner-facing sentence needs, and what this helper must not know. Extracted at the
    fourth copy (P2c T3 review).

    ``on_client`` receives the client that was built (or passed) so the caller can keep it: the
    lazy client is the caller's to hold, not this function's.
    """
    try:
        async with asyncio.timeout(deadline_s):
            if client is None:
                client = build_chat_model(model_name)
                on_client(client)
            message = await retry_on_transient(
                lambda: client.ainvoke(prompt),  # type: ignore[attr-defined]
                max_attempts=_TRANSIENT_ATTEMPTS,
                max_delay_s=_TRANSIENT_MAX_DELAY_S,
            )
    except TimeoutError as exc:
        raise ModelCallTimedOutError(f"model call ran past {deadline_s}s") from exc
    except Exception as exc:
        raise ModelCallFailedError("model call failed") from exc
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else str(content)
