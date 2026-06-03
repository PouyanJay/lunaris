"""The live ``ILessonReviser``: Claude authors the first pass and revises with cut-claim feedback.

First-pass authoring delegates to the existing ``ClaudeModuleAuthor`` (same arc prompt + parser);
revision re-issues that same personalized arc prompt with the cut claims folded in (via
``build_authoring_prompt(..., cut_claims=...)``), so the model grounds or replaces them, keeping
the arc — expects, the four phases, and self-check — intact, and the personalization preserved.
The Anthropic client is built lazily, so the reviser needs no API key to build (the deterministic
CI path uses the stub instead).
"""

from collections.abc import Callable, Sequence

import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import CourseBrief, Module

from ...subagents.module_author import ClaudeModuleAuthor, LessonDraft, build_authoring_prompt
from ...subagents.module_author.parser import parse_lesson

logger = structlog.get_logger()


class ClaudeLessonReviser:
    """Authors and revises a module's lesson with Claude (worker tier), lazily building its client.

    Delegates first-pass authoring to ``ClaudeModuleAuthor`` so the arc prompt stays in one place;
    revision reuses that same prompt with the cut claims folded in, so the personalization (the
    module's competency, the level, the frontier, the voice) is preserved across the revision.
    """

    def __init__(
        self, model: str, client_factory: Callable[[str], BaseChatModel] | None = None
    ) -> None:
        self._model = model
        self._client_factory = client_factory
        self._author = ClaudeModuleAuthor(model)
        self._client: BaseChatModel | None = None

    async def author(
        self,
        module: Module,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> LessonDraft:
        return await self._author.author(module, brief=brief, frontier=frontier)

    async def revise(
        self,
        module: Module,
        cut_claims: Sequence[str],
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> LessonDraft:
        prompt = build_authoring_prompt(
            module, brief=brief, frontier=frontier, cut_claims=list(cut_claims)
        )
        message = await retry_on_rate_limit(lambda: self._ensure_client().ainvoke(prompt))
        content = message.content if isinstance(message.content, str) else str(message.content)
        draft = parse_lesson(content)
        logger.info("lesson_revised", module=module.id, cut_claim_count=len(cut_claims))
        return draft

    def _ensure_client(self) -> BaseChatModel:
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory(self._model)
            else:
                from langchain_anthropic import ChatAnthropic

                self._client = ChatAnthropic(  # type: ignore[call-arg]
                    model=self._model,
                    default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                    max_retries=LLM_MAX_RETRIES,
                    rate_limiter=get_llm_rate_limiter(),
                )
        return self._client
