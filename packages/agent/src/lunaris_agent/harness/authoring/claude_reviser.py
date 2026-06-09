"""The live ``ILessonReviser``: Claude authors the first pass and revises with cut-claim feedback.

Both passes build the same personalized arc prompt (``build_authoring_prompt``): the first pass
optionally with the retrieved corpus evidence in front of the author (CQ Phase 1.5 grounded
authoring), revision additionally with the cut claims folded in — so the model grounds or replaces
them, keeping the arc — expects, the four phases, and self-check — intact, and the personalization
preserved. The Anthropic client is built lazily, so the reviser needs no API key to build (the
deterministic CI path uses the stub instead).
"""

from collections.abc import Callable, Sequence

import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_runtime.resilience import (
    build_chat_model,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import CourseBrief, Module

from ...subagents.module_author import LessonDraft, build_authoring_prompt
from ...subagents.module_author.parser import parse_lesson

logger = structlog.get_logger()


class ClaudeLessonReviser:
    """Authors and revises a module's lesson with Claude (worker tier), lazily building its client.

    Both passes go through ``build_authoring_prompt`` so the arc prompt stays in one place and the
    personalization (the module's competency, the level, the frontier, the voice) — plus the
    retrieved grounding evidence (CQ Phase 1.5) — is preserved across author and revise.
    """

    def __init__(
        self, model: str, client_factory: Callable[[str], BaseChatModel] | None = None
    ) -> None:
        self._model = model
        self._client_factory = client_factory
        self._client: BaseChatModel | None = None

    async def author(
        self,
        module: Module,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
        grounded_evidence: str = "",
    ) -> LessonDraft:
        prompt = build_authoring_prompt(
            module, brief=brief, frontier=frontier, grounded_evidence=grounded_evidence
        )
        draft = await self._author_from_prompt(prompt)
        logger.info("module_authored", module=module.id, grounded_len=len(grounded_evidence))
        return draft

    async def revise(
        self,
        module: Module,
        cut_claims: Sequence[str],
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
        grounded_evidence: str = "",
    ) -> LessonDraft:
        prompt = build_authoring_prompt(
            module,
            brief=brief,
            frontier=frontier,
            cut_claims=list(cut_claims),
            grounded_evidence=grounded_evidence,
        )
        draft = await self._author_from_prompt(prompt)
        logger.info("lesson_revised", module=module.id, cut_claim_count=len(cut_claims))
        return draft

    async def _author_from_prompt(self, prompt: str) -> LessonDraft:
        message = await retry_on_rate_limit(lambda: self._ensure_client().ainvoke(prompt))
        content = message.content if isinstance(message.content, str) else str(message.content)
        return parse_lesson(content)

    def _ensure_client(self) -> BaseChatModel:
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory(self._model)
            else:
                self._client = build_chat_model(self._model)
        return self._client
