"""The live ``ILessonReviser``: Claude authors the first pass and revises with cut-claim feedback.

First-pass authoring delegates to the existing ``ClaudeModuleAuthor`` (same prompt + parser the
orchestrator used); revision re-issues that author's prompt with an appended instruction listing the
claims the verifier cut, so the model grounds or replaces them rather than re-emitting the same
unsupported text. The Anthropic client is built lazily, so constructing the reviser needs no API key
(the deterministic CI path uses the stub instead).
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
from lunaris_runtime.schema import Module

from ...subagents.module_author import ClaudeModuleAuthor, LessonDraft
from ...subagents.module_author.parser import parse_lesson

logger = structlog.get_logger()

_REVISE_PROMPT = """You previously authored a Merrill lesson for the module "{title}".
These factual claims could not be grounded against the evidence corpus and were CUT:
{claims}

Re-author the lesson so each cut claim is either restated as a verifiable, well-known fact or
replaced with one. Keep the four Merrill phases (activate, demonstrate, apply, integrate) and the
rest of the lesson intact.

Respond with ONLY this JSON, no prose:
{{"activate": {{"prose": "...", "claims": ["..."]}},
  "demonstrate": {{"prose": "...", "claims": ["..."]}},
  "apply": {{"prose": "...", "claims": ["..."]}},
  "integrate": {{"prose": "...", "claims": ["..."]}}}}"""


class ClaudeLessonReviser:
    """Authors and revises a module's lesson with Claude (worker tier), lazily building its client.

    Delegates first-pass authoring to ``ClaudeModuleAuthor`` so the prompt stays in one place; owns
    only the revision prompt that feeds the cut claims back to the model.
    """

    def __init__(
        self, model: str, client_factory: Callable[[str], BaseChatModel] | None = None
    ) -> None:
        self._model = model
        self._client_factory = client_factory
        self._author = ClaudeModuleAuthor(model)
        self._client: BaseChatModel | None = None

    async def author(self, module: Module) -> LessonDraft:
        return await self._author.author(module)

    async def revise(self, module: Module, cut_claims: Sequence[str]) -> LessonDraft:
        prompt = _REVISE_PROMPT.format(
            title=module.title, claims="\n".join(f"- {claim}" for claim in cut_claims)
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
