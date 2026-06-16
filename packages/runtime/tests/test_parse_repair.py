"""invoke_with_parse_repair: bounded repair turns around a one-shot LLM parse.

The generic resilience primitive behind every "model emits text → strict parse" call site:
a response the parser rejects earns a re-prompt with the error folded in, instead of one bad
generation failing the whole build.
"""

import pytest
from lunaris_runtime.resilience import invoke_with_parse_repair

_REPAIR = "\n\nREPAIR: {error}"


class _ScriptedInvoke:
    """Replays scripted response texts and records every prompt sent."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("scripted invoke exhausted — unexpected extra call")
        return self._responses.pop(0)


def _parse_ok_marker(content: str) -> str:
    if content != "ok":
        raise ValueError(f"bad content {content!r}")
    return content


async def test_returns_the_parsed_value_after_a_repair_turn() -> None:
    # Arrange — the first response fails the parser, the second passes.
    invoke = _ScriptedInvoke(["broken", "ok"])

    # Act
    result = await invoke_with_parse_repair(
        invoke, "PROMPT", _parse_ok_marker, repair_instruction=_REPAIR
    )

    # Assert — repaired instead of raising; the repair turn restates prompt + error.
    assert result == "ok"
    assert invoke.prompts == ["PROMPT", "PROMPT" + _REPAIR.format(error="bad content 'broken'")]


async def test_raises_the_parse_error_after_exhausting_max_attempts() -> None:
    # Arrange — every response fails the parser.
    invoke = _ScriptedInvoke(["broken"] * 3)

    # Act / Assert — the final parse error surfaces after exactly max_attempts calls.
    with pytest.raises(ValueError, match="bad content"):
        await invoke_with_parse_repair(
            invoke, "PROMPT", _parse_ok_marker, repair_instruction=_REPAIR, max_attempts=3
        )
    assert len(invoke.prompts) == 3

    # Assert — feedback never stacks: every repair turn rebuilds from the original prompt,
    # so identical errors produce identical repair prompts.
    original, first_repair, second_repair = invoke.prompts
    assert original == "PROMPT"
    assert first_repair == second_repair
    assert first_repair.startswith("PROMPT")


async def test_a_clean_first_response_makes_exactly_one_call() -> None:
    # Arrange
    invoke = _ScriptedInvoke(["ok"])

    # Act
    result = await invoke_with_parse_repair(
        invoke, "PROMPT", _parse_ok_marker, repair_instruction=_REPAIR
    )

    # Assert
    assert result == "ok"
    assert invoke.prompts == ["PROMPT"]


async def test_the_default_budget_allows_a_fourth_attempt() -> None:
    # Arrange — three failures then a pass: only a budget of >= 4 reaches the good reply. The
    # default was bumped 3 -> 4 (quality-hardening B3) to give a codegen parse one more chance
    # before a hard build failure; this pins the default behaviour without passing max_attempts.
    invoke = _ScriptedInvoke(["broken", "broken", "broken", "ok"])

    # Act
    result = await invoke_with_parse_repair(
        invoke, "PROMPT", _parse_ok_marker, repair_instruction=_REPAIR
    )

    # Assert — the fourth attempt returns the parsed value (a budget of 3 would have raised).
    assert result == "ok"
    assert len(invoke.prompts) == 4


async def test_a_targeted_hint_is_appended_to_the_repair_prompt() -> None:
    # Arrange — a caller-supplied hint maps a known error to extra, error-specific guidance. The
    # primitive stays domain-agnostic: the caller decides what (if anything) a given error earns.
    invoke = _ScriptedInvoke(["broken", "ok"])

    # Act
    result = await invoke_with_parse_repair(
        invoke,
        "PROMPT",
        _parse_ok_marker,
        repair_instruction=_REPAIR,
        targeted_hint=lambda error: "TARGETED: close it" if "bad content" in error else None,
    )

    # Assert — the hint fires only on the repair turn, never the original call; the repair turn
    # carries the generic instruction AND the targeted hint, with the hint last.
    assert result == "ok"
    assert "TARGETED" not in invoke.prompts[0]
    repair_prompt = invoke.prompts[1]
    assert _REPAIR.format(error="bad content 'broken'") in repair_prompt
    assert repair_prompt.endswith("TARGETED: close it")


async def test_no_targeted_hint_when_the_hook_returns_none() -> None:
    # Arrange — an error the hint doesn't recognise (returns None) leaves the repair prompt exactly
    # as the generic fallback, so an unknown error class is never decorated with a wrong hint.
    invoke = _ScriptedInvoke(["broken", "ok"])

    # Act
    await invoke_with_parse_repair(
        invoke,
        "PROMPT",
        _parse_ok_marker,
        repair_instruction=_REPAIR,
        targeted_hint=lambda _error: None,
    )

    # Assert — identical to the no-hint path: prompt + the generic repair instruction, nothing more.
    assert invoke.prompts[1] == "PROMPT" + _REPAIR.format(error="bad content 'broken'")


async def test_a_non_parse_error_propagates_immediately_without_repair() -> None:
    # Arrange — the invoke itself fails (e.g. a network error), which is not a parse rejection.
    calls = 0

    async def failing_invoke(prompt: str) -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("connection refused")

    # Act / Assert — no repair turn is spent on it.
    with pytest.raises(RuntimeError, match="connection refused"):
        await invoke_with_parse_repair(
            failing_invoke, "PROMPT", _parse_ok_marker, repair_instruction=_REPAIR
        )
    assert calls == 1
