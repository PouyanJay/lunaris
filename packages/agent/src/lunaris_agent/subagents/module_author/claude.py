import structlog
from lunaris_runtime.resilience import (
    build_anthropic_chat_model,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import CourseBrief, Module

from .lesson_draft import LessonDraft
from .parser import parse_lesson
from .prompt import build_authoring_prompt

logger = structlog.get_logger()


class ClaudeModuleAuthor:
    """Live module author backed by Claude (D1: worker tier). Lazy client."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def author(
        self,
        module: Module,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> LessonDraft:
        if self._client is None:
            self._client = build_anthropic_chat_model(self._model_name)

        # The arc is personalized when the brief/frontier are present (the agent path); the legacy
        # orchestrator calls author(module) and gets the generic arc.
        prompt = build_authoring_prompt(module, brief=brief, frontier=frontier)
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
