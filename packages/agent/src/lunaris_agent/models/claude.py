from lunaris_runtime.resilience import LLM_MAX_RETRIES, LLM_REQUEST_TIMEOUT_S


class ClaudeModel:
    """Claude adapter (D1). The client is created lazily so constructing a router
    never requires an API key — only an actual ``complete`` call does."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def complete(self, prompt: str) -> str:
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model_name,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
            )
        message = await self._client.ainvoke(prompt)  # type: ignore[attr-defined]
        content = message.content
        return content if isinstance(content, str) else str(content)
