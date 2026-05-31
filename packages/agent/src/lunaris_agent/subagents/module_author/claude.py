import structlog
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import Module

from .lesson_draft import LessonDraft
from .parser import parse_lesson

logger = structlog.get_logger()

_PROMPT = """Author one lesson for a course module using Merrill's First Principles.

Module: "{title}"
Learning objectives:
{objectives}

Write the lesson as FOUR phases:
- activate: connect to prior knowledge / a relatable real-world problem
- demonstrate: show the concept (explain it clearly) — this is the core teaching
- apply: a guided practice step the learner does
- integrate: how the learner transfers this to their own context

For each phase, write concise prose, and list every factual sentence (claims that
could be fact-checked) separately in "claims" so they can be verified.

Respond with ONLY this JSON, no prose:
{{"activate": {{"prose": "...", "claims": ["..."]}},
  "demonstrate": {{"prose": "...", "claims": ["..."]}},
  "apply": {{"prose": "...", "claims": ["..."]}},
  "integrate": {{"prose": "...", "claims": ["..."]}}}}"""


class ClaudeModuleAuthor:
    """Live module author backed by Claude (D1: worker tier). Lazy client."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def author(self, module: Module) -> LessonDraft:
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model_name,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
                rate_limiter=get_llm_rate_limiter(),
            )

        objectives = "\n".join(f"- {o.statement}" for o in module.objectives)
        prompt = _PROMPT.format(title=module.title, objectives=objectives)
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        draft = parse_lesson(content)
        logger.info(
            "module_authored",
            module=module.id,
            claim_count=sum(
                len(s.claims)
                for s in (draft.activate, draft.demonstrate, draft.apply, draft.integrate)
            ),
        )
        return draft
