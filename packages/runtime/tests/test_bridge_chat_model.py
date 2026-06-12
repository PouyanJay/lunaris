"""BridgeChatModel wire contract (device-build-bridge T2).

The scripted keyless pipeline's subagents call ``ainvoke`` with plain prompts (and occasionally
richer message lists); everything must reach the tab as OpenAI-style role/content pairs, and the
tab's text must come back as a normal AIMessage — the subagents can't tell the bridge from any
other chat model.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from lunaris_runtime.device_bridge import DeviceBridge
from lunaris_runtime.device_bridge.chat_model import BridgeChatModel


async def _serve_next(bridge: DeviceBridge, text: str) -> list[dict[str, str]]:
    """Answer the next parked completion with ``text``; returns the wire messages the tab saw."""
    claimed = await bridge.claim(wait_s=1.0)
    assert claimed, "the tab's claim returned nothing — no completion was queued in time"
    bridge.resolve(claimed[0].request_id, text)
    return [dict(message) for message in claimed[0].messages]


async def test_a_plain_prompt_reaches_the_tab_as_a_user_message() -> None:
    # Arrange
    bridge = DeviceBridge(run_id="run-1")
    model = BridgeChatModel(bridge=bridge)
    tab = asyncio.create_task(_serve_next(bridge, "the tab's answer"))

    # Act — exactly how the scripted subagents call their client.
    reply = await model.ainvoke("Explain arrays.")

    # Assert
    assert isinstance(reply, AIMessage)
    assert reply.content == "the tab's answer"
    assert await tab == [{"role": "user", "content": "Explain arrays."}]


async def test_message_types_map_to_their_wire_roles() -> None:
    # Arrange
    bridge = DeviceBridge(run_id="run-1")
    model = BridgeChatModel(bridge=bridge)
    tab = asyncio.create_task(_serve_next(bridge, "ok"))

    # Act — system + human + a prior assistant turn (few-shot style), in one history.
    await model.ainvoke(
        [
            SystemMessage(content="You are an author."),
            HumanMessage(content="Write a lesson."),
            AIMessage(content="Here is a draft."),
        ]
    )

    # Assert — OpenAI-style roles, in order, content verbatim.
    assert await tab == [
        {"role": "system", "content": "You are an author."},
        {"role": "user", "content": "Write a lesson."},
        {"role": "assistant", "content": "Here is a draft."},
    ]


async def test_content_block_lists_are_flattened_to_their_text() -> None:
    # Arrange — some LangChain paths hand content as a block list, not a string.
    bridge = DeviceBridge(run_id="run-1")
    model = BridgeChatModel(bridge=bridge)
    tab = asyncio.create_task(_serve_next(bridge, "ok"))

    # Act
    await model.ainvoke(
        [
            HumanMessage(
                content=[
                    {"type": "text", "text": "part one. "},
                    {"type": "text", "text": "part two."},
                ]
            )
        ]
    )

    # Assert
    assert await tab == [{"role": "user", "content": "part one. part two."}]


def test_the_sync_path_is_explicitly_unsupported() -> None:
    # The bridge lives on the API's event loop; a sync .invoke() would deadlock waiting for a
    # poll that can never be served. It must fail loudly, not hang.
    model = BridgeChatModel(bridge=DeviceBridge(run_id="run-1"))

    with pytest.raises(NotImplementedError):
        model.invoke("ping")
