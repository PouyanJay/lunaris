"""The one whole-answer model call every Live caller shares (P2c T3, extracted at the fourth copy).

What it owes its callers: the deadline wraps the whole call, retries included; a hang and a refusal
are two different failures (the callers log them differently, and an operator needs to tell "the
provider is slow" from "the provider is down"); and the client built on first use is handed back to
be kept, so a caller does not rebuild it — and re-authenticate — on every turn.
"""

import asyncio
from importlib import import_module

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.session import ModelCallFailedError, ModelCallTimedOutError, ask_model

# The package re-exports the function under the module's name, so the module itself is reached by
# import path rather than by attribute.
ask_model_module = import_module("lunaris_live.session.ask_model")


class Answers:
    def __init__(self, reply: str = "words") -> None:
        self.calls = 0
        self._reply = reply

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.calls += 1
        return AIMessage(content=self._reply)


async def test_a_hang_is_a_timeout_and_a_refusal_is_a_failure() -> None:
    class Hangs:
        async def ainvoke(self, prompt: str) -> AIMessage:
            await asyncio.sleep(10)
            return AIMessage(content="late")

    class Refuses:
        async def ainvoke(self, prompt: str) -> AIMessage:
            raise RuntimeError("no")

    with pytest.raises(ModelCallTimedOutError):
        await ask_model(
            Hangs(), model_name="m", prompt="p", deadline_s=0.05, on_client=lambda c: None
        )
    with pytest.raises(ModelCallFailedError):
        await ask_model(
            Refuses(), model_name="m", prompt="p", deadline_s=1.0, on_client=lambda c: None
        )


async def test_the_client_built_on_first_use_is_handed_back_to_be_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[Answers] = []

    def build(model_name: str) -> Answers:
        client = Answers()
        built.append(client)
        return client

    monkeypatch.setattr(ask_model_module, "build_chat_model", build)
    kept: list[object] = []

    first = await ask_model(None, model_name="m", prompt="p", deadline_s=1.0, on_client=kept.append)
    # A caller that keeps what it was handed passes it back next time, and nothing is rebuilt.
    second = await ask_model(
        kept[0], model_name="m", prompt="p", deadline_s=1.0, on_client=kept.append
    )

    assert (first, second) == ("words", "words")
    assert len(built) == 1
    assert kept == [built[0]]
    assert built[0].calls == 2


async def test_the_words_come_back_as_text() -> None:
    said = await ask_model(
        Answers("hello"), model_name="m", prompt="p", deadline_s=1.0, on_client=lambda c: None
    )
    assert said == "hello"
