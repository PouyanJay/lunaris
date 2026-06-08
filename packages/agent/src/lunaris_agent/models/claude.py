from lunaris_runtime.resilience import (
    build_anthropic_chat_model,
)


class ClaudeModel:
    """Claude adapter (D1). The client is created lazily so constructing a router
    never requires an API key — only an actual ``complete`` call does."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def complete(self, prompt: str) -> str:
        if self._client is None:
            self._client = build_anthropic_chat_model(self._model_name)
        message = await self._client.ainvoke(prompt)  # type: ignore[attr-defined]
        content = message.content
        return content if isinstance(content, str) else str(content)
