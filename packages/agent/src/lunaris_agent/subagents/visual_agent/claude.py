from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    retry_on_rate_limit,
)

from .draft import VisualDraft
from .parser import parse_visual

_PROMPT = """You decide whether a concept is clarified by a diagram, and if so draw one.

Concept: "{concept}"
Teaching text:
{context}

Apply Mayer's coherence principle: only produce a diagram if it genuinely lowers the
mental effort of understanding this concept (a process, a flow, a state machine, a
relationship). If a diagram would be decorative, respond with exactly: NONE

Otherwise respond with ONLY a Mermaid code block, no prose. Prefer `graph TD`/`flowchart`
for processes. Keep it to the essential nodes (signaling — highlight the key path)."""


class ClaudeVisualGenerator:
    """Live visual generator backed by Claude (D1: worker tier). Lazy client.

    Returns ``None`` when Claude declines a diagram or the response is unparseable, so the
    engine never ships a decorative or broken visual.
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def generate(self, concept: str, context: str) -> VisualDraft | None:
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model_name,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
            )

        prompt = _PROMPT.format(concept=concept, context=context)
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        return parse_visual(content)
