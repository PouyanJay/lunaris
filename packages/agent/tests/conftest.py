"""Shared test helpers for the agent package."""

from collections.abc import Callable, Sequence
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import BaseMessage
from lunaris_runtime.schema import AgentEvent, ProgressEvent


class ScriptedChatModel(GenericFakeChatModel):
    """A fake chat model that replays a scripted message list and accepts ``bind_tools``.

    The deep-agent factory binds tools to the model before invoking it; the stock fake raises
    on ``bind_tools``. Returning ``self`` lets a fixed script drive the real harness
    (plan → tool call → finish) with no API key — the deterministic CI driver for the agent loop.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":  # type: ignore[override]
        return self


class RecordingProgressSink:
    """An IProgressSink that captures the coarse stage events for assertion."""

    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    async def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)


class RecordingAgentSink:
    """An IAgentSink that captures the fine-grained transcript events for assertion."""

    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


@pytest.fixture
def scripted_model() -> Callable[[Sequence[BaseMessage]], ScriptedChatModel]:
    """Return a factory that builds a ScriptedChatModel from a list of messages to replay."""

    def make(messages: Sequence[BaseMessage]) -> ScriptedChatModel:
        return ScriptedChatModel(messages=iter(messages))

    return make


@pytest.fixture
def progress_sink() -> RecordingProgressSink:
    """A fresh recording IProgressSink (captures the coarse stage stream)."""
    return RecordingProgressSink()


@pytest.fixture
def agent_sink() -> RecordingAgentSink:
    """A fresh recording IAgentSink (captures the fine-grained transcript stream)."""
    return RecordingAgentSink()
