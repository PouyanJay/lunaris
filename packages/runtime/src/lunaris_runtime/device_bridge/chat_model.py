"""A chat model whose completions are served by the learner's browser over the device bridge.

Returned by ``build_chat_model`` when a device bridge is in the run scope (a keyless Draft build
whose learner chose "This device"). The keyless path is the scripted pipeline, whose every model
use is a plain ``ainvoke(prompt)`` → text — so the bridge wire contract is deliberately
messages-in → text-out, with no tool-call serialization.

``langchain_core`` is imported at module top: like ``repaired_chat_model``, this module is itself
imported lazily (only on the device-bridge path), keeping ``lunaris_runtime``'s hot import path
light.
"""

from typing import TYPE_CHECKING, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from .bridge import DeviceBridge

if TYPE_CHECKING:
    from langchain_core.callbacks import (
        AsyncCallbackManagerForLLMRun,
        CallbackManagerForLLMRun,
    )


def _wire_role(message: BaseMessage) -> str:
    """The OpenAI-style role the tab's chat-completions engine expects.

    The catch-all is ``user``: tool/function messages never occur on the scripted text-only
    path, so any unrecognized message type is a plain prompt by construction."""
    if isinstance(message, SystemMessage):
        return "system"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, HumanMessage):
        return "user"
    return "user"


def _wire_text(message: BaseMessage) -> str:
    """The message's plain text. Content-block lists are joined on their text parts."""
    if isinstance(message.content, str):
        return message.content
    parts = [
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in message.content
    ]
    return "".join(parts)


class BridgeChatModel(BaseChatModel):
    """Chat model that parks each completion on the run's :class:`DeviceBridge` and awaits the
    text the learner's tab posts back."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bridge: DeviceBridge

    @property
    def _llm_type(self) -> str:
        return "lunaris-device-bridge"

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: "AsyncCallbackManagerForLLMRun | None" = None,
        **kwargs: Any,
    ) -> ChatResult:
        wire = [{"role": _wire_role(m), "content": _wire_text(m)} for m in messages]
        text = await self.bridge.complete(wire)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: "CallbackManagerForLLMRun | None" = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError(
            "the device bridge is async-only — builds run on the API's event loop"
        )
