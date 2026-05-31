import structlog
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import PrerequisiteGraph

from .parser import parse_curriculum
from .plan import CurriculumPlan

logger = structlog.get_logger()

_PROMPT = """You are a curriculum architect applying BACKWARD DESIGN.

You are given knowledge components (KCs) in their validated teaching order. Group
adjacent KCs into coherent modules, and for EACH KC write one measurable learning
objective and the assessment items that will prove it — BEFORE any lesson content.

Teaching order (earliest first):
{ordered_kcs}

Rules:
- Every KC gets exactly one objective. Phrase it "Given <context>, the learner can
  <verb> ...", using a verb that matches its Bloom level (remember, understand,
  apply, analyze, evaluate, create).
- Every objective gets at least one assessment item prompt that measures it.
- Keep modules in the given order; do not move a KC before its prerequisites.

Respond with ONLY this JSON, no prose:
{{"modules": [{{"title": "...", "kcs": ["kc_id", ...], "objectives": [
  {{"kc": "kc_id", "statement": "Given ..., the learner can ...",
    "bloom_level": "apply", "item_prompts": ["..."]}}]}}]}}"""


class ClaudeCurriculumArchitect:
    """Live curriculum architect backed by Claude (D1: strong tier). Lazy client."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def design(self, graph: PrerequisiteGraph) -> CurriculumPlan:
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model_name,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
                rate_limiter=get_llm_rate_limiter(),
            )

        labels = {kc.id: kc.label for kc in graph.nodes}
        ordered = "\n".join(
            f"{i + 1}. {kc_id} — {labels.get(kc_id, kc_id)}"
            for i, kc_id in enumerate(graph.topo_order)
        )
        prompt = _PROMPT.format(ordered_kcs=ordered)
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        plan = parse_curriculum(content, known_kc_ids=set(labels))
        logger.info(
            "curriculum_designed",
            module_count=len(plan.modules),
            objective_count=sum(len(m.objectives) for m in plan.modules),
        )
        return plan
