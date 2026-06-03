import structlog
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import CourseBrief

from .extraction import Extraction
from .parser import parse_extraction
from .prompt import build_extraction_prompt

logger = structlog.get_logger()


class ClaudeConceptExtractor:
    """Live concept extractor backed by Claude (D1: worker tier). Lazy client."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def extract(
        self,
        topic: str,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> Extraction:
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model_name,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
                rate_limiter=get_llm_rate_limiter(),
            )

        prompt = build_extraction_prompt(topic, brief, frontier or [])
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        extraction = parse_extraction(content)
        logger.info(
            "concept_extraction_completed",
            topic=topic,
            kc_count=len(extraction.kcs),
            goal=extraction.goal_id,
            target_level=brief.target_level.value if brief is not None else None,
        )
        return extraction
