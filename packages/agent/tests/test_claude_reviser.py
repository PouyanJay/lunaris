"""ClaudeLessonReviser parse-repair: one bad generation must not kill a build.

A live build once failed at its last step because a revision response carried only the
``activate`` phase: ``parse_lesson`` raised, nothing retried, and the whole run was marked
FAILED. The reviser now re-prompts with the parse error folded in (a bounded repair turn)
before giving up.
"""

import json

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from lunaris_agent.harness.authoring import ClaudeLessonReviser
from lunaris_runtime.schema import Module

_PHASE = {"prose": "Binary search halves the interval.", "claims": ["it halves the interval"]}

# The prod failure mode verbatim: the model stopped after the first phase, so the salvaged JSON
# object parses but misses demonstrate/apply/integrate.
_ACTIVATE_ONLY = json.dumps({"activate": _PHASE})

_COMPLETE_LESSON = json.dumps(
    {"activate": _PHASE, "demonstrate": _PHASE, "apply": _PHASE, "integrate": _PHASE}
)


class _ScriptedChatModel:
    """A minimal chat-model double: replays scripted responses and records every prompt.

    Not the conftest ``ScriptedChatModel``: the reviser only calls ``ainvoke`` (no tool binding),
    and these tests need the recorded prompts to assert repair-prompt content.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("scripted model exhausted — unexpected extra call")
        return AIMessage(content=self._responses.pop(0))


def _reviser(client: _ScriptedChatModel, **kwargs: int) -> ClaudeLessonReviser:
    def factory(model: str) -> BaseChatModel:
        return client  # type: ignore[return-value]  # duck-typed double: only ainvoke is used

    return ClaudeLessonReviser("claude-test", client_factory=factory, **kwargs)


def _module() -> Module:
    return Module(id="m3", title="Complexity Analysis", kcs=["big-o"], difficulty_index=0.5)


async def test_revise_repairs_an_incomplete_lesson_instead_of_failing() -> None:
    # Arrange — first response reproduces the failure (activate only), the second is complete.
    client = _ScriptedChatModel([_ACTIVATE_ONLY, _COMPLETE_LESSON])
    reviser = _reviser(client)

    # Act
    draft = await reviser.revise(_module(), ["binary search is O(log n)"])

    # Assert — the repaired lesson came back instead of a raised parse error.
    assert draft.demonstrate.prose == _PHASE["prose"]
    assert len(client.prompts) == 2


async def test_revise_sends_the_parse_error_with_the_original_prompt_on_repair() -> None:
    # Arrange
    client = _ScriptedChatModel([_ACTIVATE_ONLY, _COMPLETE_LESSON])
    reviser = _reviser(client)

    # Act — revise() is the call path that failed in production.
    await reviser.revise(_module(), ["binary search is O(log n)"])

    # Assert — the repair turn restates the full original prompt plus the parse error.
    first_prompt, repair_prompt = client.prompts
    assert repair_prompt.startswith(first_prompt)
    assert "missing Merrill phase(s)" in repair_prompt
    assert "demonstrate" in repair_prompt


async def test_author_raises_after_exhausting_bounded_repair_attempts() -> None:
    # Arrange — every response is incomplete, so repair can never succeed.
    client = _ScriptedChatModel([_ACTIVATE_ONLY] * 3)
    reviser = _reviser(client, max_attempts=3)

    # Act / Assert — the parse error surfaces after exactly max_attempts calls.
    with pytest.raises(ValueError, match="missing Merrill phase"):
        await reviser.author(_module())
    assert len(client.prompts) == 3

    # Assert — repair feedback never stacks: every repair turn rebuilds from the original
    # prompt, so identical errors produce identical repair prompts.
    original_prompt, first_repair, second_repair = client.prompts
    assert first_repair == second_repair
    assert first_repair.startswith(original_prompt)
