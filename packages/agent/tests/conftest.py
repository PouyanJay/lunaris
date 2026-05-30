"""Shared test helpers for the agent package."""

from collections.abc import Callable, Sequence
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import BaseMessage


class ScriptedChatModel(GenericFakeChatModel):
    """A fake chat model that replays a scripted message list and accepts ``bind_tools``.

    The deep-agent factory binds tools to the model before invoking it; the stock fake raises
    on ``bind_tools``. Returning ``self`` lets a fixed script drive the real harness
    (plan → tool call → finish) with no API key — the deterministic CI driver for the agent loop.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":  # type: ignore[override]
        return self


@pytest.fixture
def scripted_model() -> Callable[[Sequence[BaseMessage]], ScriptedChatModel]:
    """Return a factory that builds a ScriptedChatModel from a list of messages to replay."""

    def make(messages: Sequence[BaseMessage]) -> ScriptedChatModel:
        return ScriptedChatModel(messages=iter(messages))

    return make
