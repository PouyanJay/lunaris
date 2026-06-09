import json
import re

import structlog
from lunaris_runtime.resilience import (
    build_chat_model,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import KnowledgeComponent

from lunaris_graph.verdict import PrereqVerdict

logger = structlog.get_logger()

_PROMPT = """You are judging prerequisite relationships between two learning concepts.

Concept A: "{a_label}" — {a_def}
Concept B: "{b_label}" — {b_def}

Is a solid grasp of A a DIRECT prerequisite for learning B? Answer true only if a
learner would struggle with B without first understanding A. Ignore weak or merely
"helpful" relationships — direct prerequisites only.

Respond with ONLY a JSON object, no prose:
{{"is_prereq": true|false, "strength": <0.0-1.0 confidence>}}"""

_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _parse_verdict(text: str) -> PrereqVerdict:
    match = _JSON_RE.search(text)
    if match is None:
        raise ValueError("no JSON object in model response")
    data = json.loads(match.group(0))
    return PrereqVerdict(
        is_prereq=bool(data["is_prereq"]),
        strength=float(data.get("strength", 0.0)),
    )


class ClaudePrereqJudge:
    """Live prerequisite judge backed by Claude (D1: worker tier).

    The client is created lazily so constructing the judge needs no API key — only
    an actual ``judge`` call does. API/auth errors propagate; only an unparseable
    response is handled conservatively (no invented edge).
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def judge(
        self, prerequisite: KnowledgeComponent, dependent: KnowledgeComponent
    ) -> PrereqVerdict:
        if self._client is None:
            self._client = build_chat_model(self._model_name)

        prompt = _PROMPT.format(
            a_label=prerequisite.label,
            a_def=prerequisite.definition,
            b_label=dependent.label,
            b_def=dependent.definition,
        )
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        try:
            return _parse_verdict(content)
        except (ValueError, KeyError, json.JSONDecodeError):
            logger.warning(
                "prereq_judge_unparseable",
                prerequisite=prerequisite.id,
                dependent=dependent.id,
            )
            return PrereqVerdict(is_prereq=False)
