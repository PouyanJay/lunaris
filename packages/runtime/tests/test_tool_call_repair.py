"""T1b (keyless-fallbacks): the tool-calling safety net — repairing malformed tool-call JSON.

A small local model (the keyless fallback) is decent on prose but its tool-call JSON is
the one residual risk: it often emits *almost*-valid arguments (a code fence, a trailing comma,
single quotes, trailing prose). LangChain surfaces those as ``invalid_tool_calls`` and the agent
can't act on them. ``repair_tool_calls`` re-parses each tolerantly and promotes the ones it can fix
to real ``tool_calls`` — so a keyless build makes progress instead of stalling the turn. Live Claude
never has invalid tool calls, so this is a no-op there.
"""

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from lunaris_runtime.resilience import repair_tool_calls
from lunaris_runtime.resilience.repaired_chat_model import _repair_result


def _invalid(name: str, raw_args: str, call_id: str = "c1") -> dict:
    return {
        "type": "invalid_tool_call",
        "id": call_id,
        "name": name,
        "args": raw_args,
        "error": "could not parse",
    }


def test_a_message_with_no_invalid_calls_is_returned_unchanged() -> None:
    # Live Claude path: a clean message has nothing to repair — identity.
    message = AIMessage(
        content="",
        tool_calls=[{"type": "tool_call", "name": "search", "args": {"q": "x"}, "id": "c1"}],
    )

    repaired = repair_tool_calls(message)

    assert repaired.tool_calls == message.tool_calls
    assert repaired.invalid_tool_calls == []


def test_trailing_comma_arguments_are_repaired_and_promoted() -> None:
    # A classic weak-model malformation: a trailing comma. The call is recovered, not dropped.
    message = AIMessage(content="", invalid_tool_calls=[_invalid("build_graph", '{"depth": 3,}')])

    repaired = repair_tool_calls(message)

    assert len(repaired.tool_calls) == 1
    call = repaired.tool_calls[0]
    assert call["name"] == "build_graph"
    assert call["args"] == {"depth": 3}
    assert call["id"] == "c1"
    assert repaired.invalid_tool_calls == []  # the repaired call left the invalid bucket


def test_code_fenced_and_single_quoted_arguments_are_repaired() -> None:
    # Markdown fences + single quotes + trailing prose around the JSON — common small-model noise.
    raw = "```json\n{'topic': 'graphs', 'n': 5}\n```\nDone."
    message = AIMessage(content="", invalid_tool_calls=[_invalid("finalize", raw)])

    repaired = repair_tool_calls(message)

    assert len(repaired.tool_calls) == 1
    assert repaired.tool_calls[0]["args"] == {"topic": "graphs", "n": 5}


def test_an_unrepairable_call_stays_invalid() -> None:
    # Pure garbage isn't promoted — it stays in invalid_tool_calls so the agent's normal handling
    # (a retry / error) still applies rather than acting on a fabricated empty payload.
    message = AIMessage(content="", invalid_tool_calls=[_invalid("x", "not json at all !!!")])

    repaired = repair_tool_calls(message)

    assert repaired.tool_calls == []
    assert len(repaired.invalid_tool_calls) == 1


def test_a_mix_repairs_only_the_recoverable_calls() -> None:
    # One repairable, one not: the good one is promoted, the bad one preserved.
    message = AIMessage(
        content="",
        invalid_tool_calls=[
            _invalid("good", '{"a": 1,}', call_id="c1"),
            _invalid("bad", "<<<>>>", call_id="c2"),
        ],
    )

    repaired = repair_tool_calls(message)

    assert [c["name"] for c in repaired.tool_calls] == ["good"]
    assert [c["id"] for c in repaired.tool_calls] == ["c1"]
    assert [c["name"] for c in repaired.invalid_tool_calls] == ["bad"]


def test_a_no_argument_tool_call_repairs_to_an_empty_object() -> None:
    # A no-arg tool's arguments are ``{}``; a malformed-but-empty payload must still be promotable,
    # not dropped as if it were garbage.
    message = AIMessage(content="", invalid_tool_calls=[_invalid("list_all", "```json\n{}\n```")])

    repaired = repair_tool_calls(message)

    assert len(repaired.tool_calls) == 1
    assert repaired.tool_calls[0]["args"] == {}


def test_arguments_that_repair_to_a_non_object_are_not_promoted() -> None:
    # Tool arguments must be a JSON object; a bare scalar/array that "repairs" is not a valid call.
    message = AIMessage(content="", invalid_tool_calls=[_invalid("x", "[1, 2, 3]")])

    repaired = repair_tool_calls(message)

    assert repaired.tool_calls == []
    assert len(repaired.invalid_tool_calls) == 1


def test_repair_result_rebuilds_the_chat_result_with_repaired_messages() -> None:
    # The model wrapper's helper (RepairingChatOpenAI._generate/_agenerate delegate to this): it
    # repairs AIMessage generations and passes non-AIMessage generations through untouched.
    ai = AIMessage(content="", invalid_tool_calls=[_invalid("build_graph", '{"depth": 3,}')])
    other = HumanMessage(content="ignored")
    result = ChatResult(generations=[ChatGeneration(message=ai), ChatGeneration(message=other)])

    repaired = _repair_result(result)

    assert repaired.generations[0].message.tool_calls[0]["args"] == {"depth": 3}
    assert repaired.generations[1].message is other  # non-AIMessage passes through unchanged
