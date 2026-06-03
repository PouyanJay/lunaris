import structlog
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import CourseBrief

from .parser import parse_profile
from .profile import LearnerProfile

logger = structlog.get_logger()

_PROMPT = """\
Given a learner's goal and level, list the foundational concepts they ALREADY know — the "frontier"
a course toward this goal must NOT re-teach.

Subject: {subject}
Goal: {goal}
Target level: {level}
Assumed prior knowledge: {assumed_prior}

A learner at this level has mastered the foundations beneath it. List the concept areas they can be
assumed to already know, so the course skips them and starts at their edge (Vygotsky's ZPD). Be
specific to the subject. For a TRUE NOVICE with no prior knowledge, return an EMPTY list — the
course should then teach from the foundations.

Respond with ONLY this JSON, no prose:
{{"frontier": ["a concept the learner already knows", "another known concept area"]}}"""


class ClaudeLearnerProfiler:
    """Live learner profiler backed by Claude (D1: worker tier). Lazy client."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def profile(self, brief: CourseBrief) -> LearnerProfile:
        if self._client is None:
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model_name,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
                rate_limiter=get_llm_rate_limiter(),
            )

        prompt = _PROMPT.format(
            subject=brief.subject,
            goal=brief.goal,
            level=brief.target_level.value,
            assumed_prior=brief.assumed_prior or "(none stated)",
        )
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        profile = parse_profile(content)
        logger.info(
            "learner_profiling_completed",
            target_level=brief.target_level.value,
            frontier_size=len(profile.frontier),
        )
        return profile
