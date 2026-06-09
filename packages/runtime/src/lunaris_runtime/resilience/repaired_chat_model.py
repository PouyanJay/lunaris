"""A ChatOpenAI that repairs the keyless model's malformed tool-call JSON (keyless-fallbacks T1b).

Used only on the keyless Bonsai fallback path — a native 1-bit model whose tool-call arguments are
the one place it slips. Overriding ``_generate``/``_agenerate`` post-processes every completion so a
recoverable ``invalid_tool_call`` becomes a real ``tool_call`` before the agent (or a
``with_structured_output`` parser) sees it. Because ``bind_tools`` / ``with_structured_output`` wrap
this same instance, the repair applies transparently no matter how the caller invokes the model.

Known limitation: this covers the non-streaming generate path. Streamed tool calls (assembled from
``tool_call_chunks``) bypass ``_agenerate`` and are not repaired here — the keyless planner runs the
generate path, and the streaming repair is left as a follow-up.

``langchain_openai`` is imported at module top, so this module is imported lazily (only on the
keyless path) to keep ``lunaris_runtime``'s hot import path free of it — see ``llm_client``.
"""

from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from .tool_call_repair import repair_tool_calls

if TYPE_CHECKING:
    from langchain_core.callbacks import (
        AsyncCallbackManagerForLLMRun,
        CallbackManagerForLLMRun,
    )
    from langchain_core.messages import BaseMessage


def _repair_result(result: ChatResult) -> ChatResult:
    """Rebuild a ChatResult with repaired tool calls on every AIMessage generation.

    A new ChatGeneration is constructed for each repaired message rather than mutating in place
    because a ChatGeneration is effectively immutable here (a pydantic model the caller may reuse);
    non-AIMessage generations pass through unchanged."""
    repaired = []
    for generation in result.generations:
        message = generation.message
        if isinstance(message, AIMessage):
            generation = ChatGeneration(
                message=repair_tool_calls(message),
                generation_info=generation.generation_info,
            )
        repaired.append(generation)
    return ChatResult(generations=repaired, llm_output=result.llm_output)


class RepairingChatOpenAI(ChatOpenAI):
    """ChatOpenAI whose completions have their malformed tool-call JSON repaired (T1b)."""

    def _generate(
        self,
        messages: "list[BaseMessage]",
        stop: "list[str] | None" = None,
        run_manager: "CallbackManagerForLLMRun | None" = None,
        **kwargs: Any,
    ) -> ChatResult:
        return _repair_result(
            super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        )

    async def _agenerate(
        self,
        messages: "list[BaseMessage]",
        stop: "list[str] | None" = None,
        run_manager: "AsyncCallbackManagerForLLMRun | None" = None,
        **kwargs: Any,
    ) -> ChatResult:
        return _repair_result(
            await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        )
