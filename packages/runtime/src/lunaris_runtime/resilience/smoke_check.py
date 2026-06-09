"""A startup tool-calling smoke check for the keyless fallback model (keyless-fallbacks T1b).

The keyless fallback (a small local model) is decent on prose but tool-calling is its one residual
risk, so before serving keyless an operator can probe it: bind one trivial tool and see whether it
emits a usable tool call. Run it as a pre-flight (see ``main`` below, or from ``make run``) rather
than in the API's request path; it is intentionally NOT wired into app startup, so the hot path and
the test suite never probe a local runtime.

Best-effort: any error (an unreachable endpoint, a client failure) returns ``UNREACHABLE`` and logs
a warning — it never raises, so a missing local runtime degrades to a warning, not a crash.
"""

from enum import StrEnum

import structlog

from .llm_client import build_keyless_chat_model

logger = structlog.get_logger()

# A minimal tool the model is asked to call — a single integer argument, so a correct response is
# unambiguous and the repair guard (T1b) has a real chance to fix a near-miss before we judge it.
_PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "echo",
        "description": "Echo back the given integer value.",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
        },
    },
}

_PROBE_PROMPT = "Call the echo tool with value 1."


class SmokeCheckResult(StrEnum):
    """The verdict of the keyless tool-calling probe."""

    OK = "ok"  # the model produced a usable tool call (post-repair) — keyless builds can tool-call
    NO_TOOL_CALL = "no_tool_call"  # reachable, but no tool call even after repair — Draft at risk
    UNREACHABLE = "unreachable"  # the endpoint couldn't be reached / errored — can't tell


def keyless_tool_calling_smoke_check() -> SmokeCheckResult:
    """Probe the keyless fallback model with one trivial tool call and report whether it tool-calls.

    Builds the keyless fallback directly (never the live Claude path), binds a trivial echo tool,
    and invokes it once. Returns :class:`SmokeCheckResult`; best-effort, so any failure is logged
    and mapped to ``UNREACHABLE`` rather than raised.
    """
    try:
        bound = build_keyless_chat_model().bind_tools([_PROBE_TOOL])
        response = bound.invoke(_PROBE_PROMPT)
    except Exception:
        logger.warning("keyless_smoke_check_unreachable", exc_info=True)
        return SmokeCheckResult.UNREACHABLE
    if getattr(response, "tool_calls", None):
        logger.info("keyless_smoke_check_ok")
        return SmokeCheckResult.OK
    logger.warning("keyless_smoke_check_no_tool_call")
    return SmokeCheckResult.NO_TOOL_CALL


def _main() -> int:
    """CLI entry: run the probe, print the verdict, and exit non-zero unless it tool-called.

    ``UNREACHABLE`` exits non-zero too (the operator asked to verify keyless and we couldn't), so a
    ``make run`` pre-flight can gate on it. Invoke as
    ``python -m lunaris_runtime.resilience.smoke_check``.
    """
    result = keyless_tool_calling_smoke_check()
    print(f"keyless tool-calling smoke check: {result.value}")
    return 0 if result is SmokeCheckResult.OK else 1


if __name__ == "__main__":
    import sys

    sys.exit(_main())
