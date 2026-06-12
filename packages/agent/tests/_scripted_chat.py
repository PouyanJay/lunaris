"""A minimal prompt-recording chat-model double for the one-prompt Claude components.

Not the conftest ``ScriptedChatModel`` (which extends ``GenericFakeChatModel`` for tool
binding): the reviser/architect components only call ``ainvoke``, and their parse-repair tests
need the recorded prompts to assert repair-prompt content.
"""

from langchain_core.messages import AIMessage


class ScriptedRecordingChatModel:
    """Replays scripted responses and records every prompt sent; fails loudly on over-call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("scripted model exhausted — unexpected extra call")
        return AIMessage(content=self._responses.pop(0))
