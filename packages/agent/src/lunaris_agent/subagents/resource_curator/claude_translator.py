import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_runtime.resilience import build_chat_model, retry_on_rate_limit
from lunaris_runtime.schema import CourseBrief, Modality, Module

from .deterministic import DeterministicQueryTranslator
from .search_query import SearchQuery
from .translator import IQueryTranslator
from .translator_parser import parse_search_queries
from .translator_prompt import build_translator_prompt

logger = structlog.get_logger()

_MAX_QUERIES = 4  # over-retrieve within the curator's search budget; the curator caps further


class ClaudeQueryTranslator:
    """The LLM query translator (worker tier) — competency → domain search vernacular (CQ Phase 2).

    Rewrites each competency into the natural search phrasing of its domain and shapes the queries
    from the course ``goal_type`` + the module's ``modality`` (a receptive competency seeks input
    material, a credential goal uses the real exam name, …), carrying ``good_result_looks_like``
    forward so the relevance judge scores CONTENT. The no-verbatim and no-hype rules are enforced in
    code (the parser), not merely asked of the model. Best-effort: any failure — model error, no
    usable JSON, or zero surviving queries — degrades to the deterministic fallback, so the build
    always has queries. ``model`` is a model id (lazy ``ChatAnthropic``, worker tier) or an injected
    chat model (tests).
    """

    def __init__(
        self,
        model: str | BaseChatModel,
        *,
        fallback: IQueryTranslator | None = None,
        max_queries: int = _MAX_QUERIES,
    ) -> None:
        self._model = model
        self._client: BaseChatModel | None = None
        self._fallback = fallback or DeterministicQueryTranslator()
        self._max_queries = max_queries

    async def translate(
        self,
        module: Module,
        brief: CourseBrief | None = None,
        *,
        modality: Modality | None = None,
        feedback: str | None = None,
    ) -> list[SearchQuery]:
        competency = module.competency or module.title
        prompt = build_translator_prompt(module, brief, modality, feedback)
        try:
            message = await retry_on_rate_limit(lambda: self._chat_model().ainvoke(prompt))
            text = message.content if isinstance(message.content, str) else str(message.content)
            queries = parse_search_queries(text, competency=competency)[: self._max_queries]
        except Exception:
            logger.warning("query_translation_failed", module=module.id, exc_info=True)
            queries = []
        if not queries:
            logger.info("query_translation_fallback", module=module.id)
            return await self._fallback.translate(
                module, brief, modality=modality, feedback=feedback
            )
        return queries

    def _chat_model(self) -> BaseChatModel:
        if not isinstance(self._model, str):
            return self._model
        if self._client is None:
            self._client = build_chat_model(self._model)
        return self._client
