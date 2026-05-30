from typing import Protocol


class ChatModel(Protocol):
    """Minimal model interface the agent depends on (DIP boundary).

    Implementations: a real Claude adapter, or a stub in tests. Keeping this a
    Protocol is what makes the model provider swappable per D1.
    """

    async def complete(self, prompt: str) -> str: ...
