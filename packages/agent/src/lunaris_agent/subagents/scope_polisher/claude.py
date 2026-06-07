import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import CourseBrief, CourseScope

from .parser import parse_polished_lines
from .prompt import build_polish_prompt
from .reconcile import reconcile_scope

logger = structlog.get_logger()


class ClaudeScopePolisher:
    """Live scope-band polisher: one Claude call that refines the wording, never the facts.

    Asks the model (worker tier) to rewrite the delivers/excludes lines into crisper copy, then
    reconciles the reply against the deterministic band so the effort and the line counts cannot
    drift — a count change, a blank line, or an unparseable reply all degrade to the original band.
    Best-effort: any error returns the band unchanged. ``model`` is a model id (lazy
    ``ChatAnthropic``, worker tier) or an injected chat model (tests).
    """

    def __init__(self, model: str | BaseChatModel) -> None:
        self._model = model
        self._client: BaseChatModel | None = None

    async def polish(self, scope: CourseScope, *, brief: CourseBrief | None) -> CourseScope:
        try:
            prompt = build_polish_prompt(scope, brief)
            message = await retry_on_rate_limit(lambda: self._chat_model().ainvoke(prompt))
            raw = message.content if isinstance(message.content, str) else str(message.content)
        except Exception:
            logger.warning("scope_polish_failed", exc_info=True)
            return scope
        parsed = parse_polished_lines(raw)
        if parsed is None:
            logger.info("scope_polish_unparsed")
            return scope
        delivers, excludes = parsed
        candidate = CourseScope(effort=scope.effort, delivers=delivers, excludes=excludes)
        return reconcile_scope(scope, candidate)

    def _chat_model(self) -> BaseChatModel:
        if not isinstance(self._model, str):
            return self._model
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
                rate_limiter=get_llm_rate_limiter(),
            )
        return self._client
