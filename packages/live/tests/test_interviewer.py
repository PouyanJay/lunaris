"""The model-backed interviewer (Lunaris Live, Phase 2c, T2).

What it is asked with, what it makes of the answer, and every way it fails, driven with a scripted
client rather than a key. The interviewer's job is to *listen*: the whole exchange history rides
the prompt verbatim, the map's arrival is said in words the model can act on, and its answer is a
question or an explicit end, never prose the loop then has to guess at.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.session import (
    ClaudeInterviewer,
    InterviewerUnavailableError,
    InterviewExchange,
)

_EXCHANGES = (
    InterviewExchange(question="Where have you met Bayes' theorem?", answer="A stats module."),
    InterviewExchange(question="What do you want to do with it?", answer="Read medical papers."),
)


class ScriptedModel:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content=self._reply)


async def test_the_interviewer_asks_the_question_the_model_wrote() -> None:
    model = ScriptedModel('{"question": "Which paper are you reading now?", "done": false}')

    asked = await ClaudeInterviewer("m", client=model).ask(
        "Bayes' theorem", exchanges=_EXCHANGES, run_id="r1"
    )

    assert asked == "Which paper are you reading now?"


async def test_the_whole_exchange_history_reaches_the_model_verbatim() -> None:
    model = ScriptedModel('{"question": "Q?", "done": false}')

    await ClaudeInterviewer("m", client=model).ask(
        "Bayes' theorem", exchanges=_EXCHANGES, run_id="r1"
    )

    prompt = model.prompts[0]
    assert "Bayes' theorem" in prompt
    for exchange in _EXCHANGES:
        assert exchange.question in prompt
        assert exchange.answer in prompt


async def test_done_is_the_end_of_the_interview() -> None:
    model = ScriptedModel('{"done": true}')

    asked = await ClaudeInterviewer("m", client=model).ask("T", exchanges=_EXCHANGES, run_id="r1")

    assert asked is None


async def test_a_done_that_still_carries_a_question_is_done() -> None:
    """The model's ``done`` outranks its habit of writing something anyway: an interview that ended
    must not sprout one more question because the model padded its JSON."""
    model = ScriptedModel('{"question": "One more thing?", "done": true}')

    assert await ClaudeInterviewer("m", client=model).ask("T", run_id="r1") is None


@pytest.mark.parametrize(
    "reply",
    ["not json at all", '{"question": "", "done": false}', '{"done": false}', "[]"],
)
async def test_an_unusable_answer_is_a_failure_the_loop_can_name(reply: str) -> None:
    """Refused rather than coerced: a blank question would be stored as a turn the learner cannot
    read (``SessionTurn.tutor`` is ``min_length=1``), and the loop has a degrade for a failure
    (end the interview) that it does not have for garbage."""
    model = ScriptedModel(reply)

    with pytest.raises(InterviewerUnavailableError):
        await ClaudeInterviewer("m", client=model).ask("T", run_id="r1")


async def test_a_model_that_hangs_is_bounded() -> None:
    class Hangs:
        async def ainvoke(self, prompt: str) -> AIMessage:
            await asyncio.sleep(10)
            return AIMessage(content="{}")

    with pytest.raises(InterviewerUnavailableError):
        await ClaudeInterviewer("m", client=Hangs(), deadline_s=0.05).ask("T", run_id="r1")


async def test_a_provider_that_errors_is_the_same_failure() -> None:
    class Errors:
        async def ainvoke(self, prompt: str) -> AIMessage:
            raise RuntimeError("boom")

    with pytest.raises(InterviewerUnavailableError):
        await ClaudeInterviewer("m", client=Errors()).ask("T", run_id="r1")
