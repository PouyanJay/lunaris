import structlog
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import CourseBrief, PrerequisiteGraph

from .parser import parse_curriculum
from .plan import CurriculumPlan
from .prompt import build_curriculum_prompt

logger = structlog.get_logger()


class ClaudeCurriculumArchitect:
    """Live curriculum architect backed by Claude (D1: strong tier). Lazy client."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def design(
        self, graph: PrerequisiteGraph, *, brief: CourseBrief | None = None
    ) -> CurriculumPlan:
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model_name,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
                rate_limiter=get_llm_rate_limiter(),
            )

        prompt = build_curriculum_prompt(graph, brief)
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        plan = parse_curriculum(content, known_kc_ids={kc.id for kc in graph.nodes})
        logger.info(
            "curriculum_designed",
            module_count=len(plan.modules),
            objective_count=sum(len(m.objectives) for m in plan.modules),
        )
        return plan
