"""Repair malformed tool-call JSON from a small local model (keyless-fallbacks T1b).

The keyless fallback's one residual risk is tool-call reliability: a small model often emits
*almost*-valid argument JSON (a markdown fence, a trailing comma, single quotes, trailing prose)
LangChain can't parse, so it lands in ``AIMessage.invalid_tool_calls`` and the agent's turn stalls.
:func:`repair_tool_calls` re-parses each with a tolerant pass and promotes the ones it can recover
to real ``tool_calls``. Live Claude never produces invalid tool calls, so this is a no-op there.

``json_repair`` is imported lazily (it's only on the keyless path), keeping this module's import
cheap and matching how the fallback model itself imports ``langchain_openai`` lazily.
"""

import json
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from langchain_core.messages import AIMessage

logger = structlog.get_logger()


def _repair_arguments(raw: object) -> dict | None:
    """Parse a raw tool-argument string into an object, repairing common weak-model malformations.

    Returns the parsed ``dict`` on success, or ``None`` when the value can't be recovered as a JSON
    object. A value that parses to a non-object (a bare scalar/array) is rejected — tool arguments
    are always an object — so the agent never acts on a structurally wrong payload.
    """
    if isinstance(raw, dict):  # already parsed (defensive — invalid_tool_calls carries a string)
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed: object = json.loads(raw)
    except (ValueError, TypeError):
        from json_repair import repair_json

        try:
            parsed = repair_json(raw, return_objects=True)
        except (ValueError, TypeError):
            return None
    # Accept any object — including an empty one (a no-argument tool call is ``{}``). A bare
    # scalar/array is rejected (tool arguments are always an object), and json_repair returns ``""``
    # for true garbage, which fails this isinstance check.
    return parsed if isinstance(parsed, dict) else None


def repair_tool_calls(message: "AIMessage") -> "AIMessage":
    """Promote repairable ``invalid_tool_calls`` to valid ``tool_calls`` on a copy of ``message``.

    Each invalid call's raw argument string is re-parsed tolerantly; a success becomes a real tool
    call (same name + id) the agent can act on, and leaves the invalid bucket. Unrecoverable calls
    stay in ``invalid_tool_calls`` so the agent's normal error/retry handling still applies. Returns
    the message unchanged when there is nothing to repair (the live-Claude path).
    """
    if not message.invalid_tool_calls:
        return message

    from langchain_core.messages.tool import tool_call as make_tool_call

    original_count = len(message.tool_calls)
    repaired_calls = list(message.tool_calls)
    still_invalid = []
    for invalid in message.invalid_tool_calls:
        args = _repair_arguments(invalid.get("args"))
        if args is not None and invalid.get("name"):
            repaired_calls.append(
                make_tool_call(name=invalid["name"], args=args, id=invalid.get("id"))
            )
        else:
            still_invalid.append(invalid)

    newly_repaired = repaired_calls[original_count:]
    if not newly_repaired:
        return message
    # Names only (never the argument values) — keyless tool args could carry course content.
    logger.info(
        "keyless_tool_calls_repaired",
        repaired=len(newly_repaired),
        names=[call["name"] for call in newly_repaired],
    )
    return message.model_copy(
        update={"tool_calls": repaired_calls, "invalid_tool_calls": still_invalid}
    )
