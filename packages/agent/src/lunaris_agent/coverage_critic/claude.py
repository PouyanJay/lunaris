"""The live coverage critic: a Claude judge over the course, with a deterministic fail-safe (P4.2).

Per owner Q2 the primary coverage gate is an LLM judge — it reads the modules' content + practice
against the promised competencies and rules which are not materially built. But the gate must never
crash or silently pass a keyless/failed build, so any error or unparseable reply degrades to the
``DeterministicCoverageCritic`` (the structural check). Mirrors the ``Verifier``'s own
assessor-with-fail-safe shape: the model judges, code guarantees the build still finishes honestly.
"""

import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import Course, CourseBrief

from .deterministic import DeterministicCoverageCritic
from .parser import parse_coverage_gaps
from .prompt import build_coverage_prompt
from .protocol import ICoverageCritic
from .report import CoverageReport

logger = structlog.get_logger()


def _promised_competencies(brief: CourseBrief | None) -> list[str]:
    """The competencies the standard promised — the genericity-safe abstraction the gate checks."""
    if brief is None or brief.research is None:
        return []
    return list(brief.research.competencies)


class ClaudeCoverageCritic:
    """LLM coverage judge (primary), degrading to the deterministic structural check on any failure.

    ``model`` is a model id (lazy ``ChatAnthropic``, strong tier — coverage is a judgement call) or
    an injected chat model (tests). With no promised competencies it returns clean without a call.
    """

    def __init__(
        self, model: str | BaseChatModel, *, fallback: ICoverageCritic | None = None
    ) -> None:
        self._model = model
        self._client: BaseChatModel | None = None
        self._fallback = fallback or DeterministicCoverageCritic()

    async def review(self, course: Course, *, brief: CourseBrief | None) -> CoverageReport:
        competencies = _promised_competencies(brief)
        if not competencies:
            return CoverageReport()
        try:
            prompt = build_coverage_prompt(competencies, course.modules)
            message = await retry_on_rate_limit(lambda: self._chat_model().ainvoke(prompt))
            raw = message.content if isinstance(message.content, str) else str(message.content)
        except Exception:
            logger.warning("coverage_review_failed", exc_info=True)
            return await self._fallback.review(course, brief=brief)
        gaps = parse_coverage_gaps(raw, set(competencies))
        if gaps is None:
            logger.info("coverage_review_unparsed", raw_preview=raw[:120])
            return await self._fallback.review(course, brief=brief)
        return CoverageReport(gaps)

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
