import structlog
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import CourseBrief

from .parser import parse_brief

logger = structlog.get_logger()

_PROMPT = """\
Interpret a course request as a GOAL for a learner at a level — NOT a subject to enumerate.

Request: "{request}"

Read what the request implies and respond with a structured brief. Infer honestly from the request;
do NOT invent the contents of any named standard (a later step researches those). Fields:
  - subject: the broad subject area (e.g. "English language proficiency")
  - goal: the concrete outcome the learner wants (e.g. "reach CLB 10 across all four skills")
  - target_standard: if the goal names an external standard, exam, or certification, an object
    {{"name": "...", "kind": "external_standard|certification|exam|informal",
    "authority_hint": "the body that defines it, e.g. ircc.canada.ca"}}; otherwise null
  - target_level: one of novice, intermediate, advanced, expert, or "n/a"
  - assumed_prior: one sentence on what the learner most likely already knows, given the goal+level
  - audience: one short phrase describing who this learner is
  - deliverable_shape: {{"lessons": <integer or null>}} — lift an explicit lesson count if the
    request states one, else null
  - needs_research: true if the target is an externally-defined standard/exam/certification whose
    real requirements matter, else false
  - domain_field: a short field tag (e.g. "language-learning", "computer-science")
  - preferences: {{"detail_depth": "concise|balanced|in_depth",
    "language_style": "simple|balanced|sophisticated|scientific"}} — infer from the request's tone;
    default "balanced" for both

Respond with ONLY this JSON, no prose:
{{"subject": "...", "goal": "...", "target_standard": null, "target_level": "n/a",
"assumed_prior": "...", "audience": "...", "deliverable_shape": {{"lessons": null}},
"needs_research": false, "domain_field": "...",
"preferences": {{"detail_depth": "balanced", "language_style": "balanced"}}}}"""


class ClaudeGoalInterpreter:
    """Live goal interpreter backed by Claude (D1: worker tier). Lazy client."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def interpret(self, request: str) -> CourseBrief:
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model_name,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
                rate_limiter=get_llm_rate_limiter(),
            )

        prompt = _PROMPT.format(request=request)
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        brief = parse_brief(content)
        logger.info(
            "goal_interpretation_completed",
            subject=brief.subject,
            target_level=brief.target_level.value,
            needs_research=brief.needs_research,
            has_standard=brief.target_standard is not None,
        )
        return brief
