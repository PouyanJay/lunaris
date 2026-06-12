from collections.abc import Callable

import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_runtime.resilience import (
    DEFAULT_PARSE_REPAIR_ATTEMPTS,
    invoke_with_parse_repair,
)
from lunaris_runtime.schema import CourseBrief, PrerequisiteGraph

from ..lazy_chat_client import LazyChatClient
from .parser import parse_curriculum
from .plan import CurriculumPlan
from .prompt import build_curriculum_prompt

logger = structlog.get_logger()

_REPAIR_INSTRUCTION = (
    "\n\nYour previous response could not be used: {error}. "
    'Respond again with the COMPLETE curriculum as a single JSON object. Every "kc" and '
    '"kcs" entry must copy a kc id from the teaching order verbatim (the id string, never '
    "the list number), every objective needs at least one assessment item, and emit no text "
    "outside the JSON object."
)


class ClaudeCurriculumArchitect:
    """Live curriculum architect backed by Claude (D1: strong tier). Lazy client.

    A response that doesn't parse into a valid curriculum (e.g. a weak keyless model echoing
    the teaching-order list number as a KC id) gets bounded repair turns — the parse error
    folded into the prompt — rather than failing the build.
    """

    def __init__(
        self,
        model: str,
        client_factory: Callable[[str], BaseChatModel] | None = None,
        *,
        max_attempts: int = DEFAULT_PARSE_REPAIR_ATTEMPTS,
    ) -> None:
        self._client = LazyChatClient(model, client_factory)
        self._max_attempts = max_attempts

    async def design(
        self, graph: PrerequisiteGraph, *, brief: CourseBrief | None = None
    ) -> CurriculumPlan:
        prompt = build_curriculum_prompt(graph, brief)
        known_kc_ids = {kc.id for kc in graph.nodes}
        plan = await invoke_with_parse_repair(
            self._client.invoke_text,
            prompt,
            lambda content: parse_curriculum(content, known_kc_ids=known_kc_ids),
            repair_instruction=_REPAIR_INSTRUCTION,
            max_attempts=self._max_attempts,
        )
        logger.info(
            "curriculum_designed",
            module_count=len(plan.modules),
            objective_count=sum(len(m.objectives) for m in plan.modules),
        )
        return plan
