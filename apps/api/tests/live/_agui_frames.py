"""Reading an AG-UI run the way a client reads it.

One place, because a run now carries more than one tool call (T3's Tier 1 card and T5's Tier 2
layout), and the naive way to reassemble arguments — concatenate every ``TOOL_CALL_ARGS`` in the
stream — splices two JSON documents into one unparseable string. A real client keys on
``toolCallId``; so does this, and it should only have to be got right once.

Deliberately plain functions over a decoded frame list rather than fixtures, so they serve a test
that drove the whole app and one that drove the translator directly.
"""

import json
from typing import Any


def call_named(events: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """One named tool call's arguments, reassembled from its own frames.

    Raises ``StopIteration`` when the run carried no such call, which is the honest failure: a test
    asking for a card or a layout that was never emitted has already found its defect, and an empty
    dict would let it go on to assert something vacuous about it.
    """
    call_id = next(
        event["toolCallId"]
        for event in events
        if event["type"] == "TOOL_CALL_START" and event["toolCallName"] == name
    )
    args = "".join(
        event["delta"]
        for event in events
        if event["type"] == "TOOL_CALL_ARGS" and event["toolCallId"] == call_id
    )
    return json.loads(args)


def tool_names(events: list[dict[str, Any]]) -> list[str]:
    """Every tool call the run made, in the order it made them."""
    return [event["toolCallName"] for event in events if event["type"] == "TOOL_CALL_START"]
