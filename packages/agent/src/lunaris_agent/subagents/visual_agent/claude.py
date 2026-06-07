from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)

from .draft import VisualDraft
from .parser import parse_visual
from .spec_parser import parse_visual_spec

_PROMPT = """You decide whether a concept is clarified by a diagram, and if so describe one.

Concept: "{concept}"
Teaching text:
{context}

Apply Mayer's coherence principle: only produce a diagram if it genuinely lowers the
mental effort of understanding this concept (a process, a flow, a state machine, a
relationship). If a diagram would be decorative, respond with exactly: NONE

Otherwise respond with a typed visual specification as a ```json block — a structured
description the app draws with its own components. Use exactly ONE shape, discriminated by a
"type" field; every shape also takes an optional "title". Field names must match exactly
(a trailing ? marks a nullable field):
- flow: nodes [{{id, label}}] + edges [{{from, to, label?}}]
- tree: nodes [{{id, label, parentId?}}]
- steps: steps [{{title, detail?}}]
- comparison: columns [str] + rows [{{label, values: [str]}}]
- timeline: events [{{label, detail?, when?}}]
- before-after: before {{label, content}} + after {{label, content}} — an interactive toggle \
between two states; choose it for a transformation (naive→optimised, before→after, problem→solution)
- worked-example: literal {{label, content}} + improved {{label, content}} + note? — a naive \
phrasing beside its improved rewrite with a note on why it is better; choose it for a concrete \
"here is the weak version, the strong version, and why" teaching example

Then add a ```mermaid block with the equivalent diagram as a fallback. Keep both to the
essential nodes (signaling — highlight the key path)."""


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
                rate_limiter=get_llm_rate_limiter(),
            )

        prompt = _PROMPT.format(concept=concept, context=context)
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)

        # The branded spec is primary; the Mermaid block is the fallback source. Decline only when
        # neither parses — never ship a half-formed visual.
        spec = parse_visual_spec(content)
        mermaid = parse_visual(content)
        if spec is None and mermaid is None:
            return None
        return VisualDraft(source=mermaid.source if mermaid else "", spec=spec)
