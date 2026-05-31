import structlog
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    retry_on_rate_limit,
)

from .extraction import Extraction
from .parser import parse_extraction

logger = structlog.get_logger()

_PROMPT = """Decompose a learning topic into its atomic knowledge components (KCs).

Topic: "{topic}"

A knowledge component is the smallest unit teachable in one sitting. List every KC a
learner must master to reach the topic, INCLUDING the foundational prerequisites they
likely need first. For each KC give:
  - id: short snake_case identifier
  - label: a human-readable name
  - definition: one sentence
  - difficulty: 0.0 (most basic) to 1.0 (the topic itself)
  - bloom_ceiling: one of remember, understand, apply, analyze, evaluate, create

The single most advanced KC — the topic itself — is the goal.

Respond with ONLY this JSON, no prose:
{{"goal_id": "<id>", "kcs": [{{"id": "...", "label": "...", "definition": "...",
"difficulty": 0.0, "bloom_ceiling": "apply"}}]}}"""


class ClaudeConceptExtractor:
    """Live concept extractor backed by Claude (D1: worker tier). Lazy client."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def extract(self, topic: str) -> Extraction:
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model_name,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
            )

        prompt = _PROMPT.format(topic=topic)
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        extraction = parse_extraction(content)
        logger.info(
            "concept_extraction_completed",
            topic=topic,
            kc_count=len(extraction.kcs),
            goal=extraction.goal_id,
        )
        return extraction
