"""The lazily-built chat client shared by the one-prompt Claude components.

Several components (the lesson reviser, the curriculum architect) hold a model id and only
build the real client on first use — so they construct without an API key (the deterministic
CI path uses stubs) and tests inject a double via the factory. This class is that pattern,
once: factory-or-default construction plus the text-in/text-out invoke the parse-repair seam
expects.
"""

from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from lunaris_runtime.resilience import build_chat_model


class LazyChatClient:
    """Builds the chat model on first use; ``invoke_text`` is prompt → response text."""

    def __init__(
        self, model: str, client_factory: Callable[[str], BaseChatModel] | None = None
    ) -> None:
        self._model = model
        self._client_factory = client_factory
        self._client: BaseChatModel | None = None

    async def invoke_text(self, prompt: str) -> str:
        message = await self._ensure_client().ainvoke(prompt)
        return message.content if isinstance(message.content, str) else str(message.content)

    def _ensure_client(self) -> BaseChatModel:
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory(self._model)
            else:
                self._client = build_chat_model(self._model)
        return self._client
