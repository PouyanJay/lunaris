import json
import re

import structlog
from lunaris_runtime.resilience import (
    build_anthropic_chat_model,
    retry_on_rate_limit,
)

from lunaris_grounding.assessors.render_evidence import render_evidence
from lunaris_grounding.evidence import Evidence, Support

logger = structlog.get_logger()

_PROMPT = """You are an INDEPENDENT fact-checker. Be skeptical: only confirm support
that the evidence actually establishes. Default to NOT supported when unsure.

Claim: "{claim}"

Evidence:
{evidence}

Does the evidence support the claim? Respond with ONLY this JSON, no prose:
{{"score": <0.0-1.0 how well the evidence supports the claim>,
  "citation_id": "<id of the single best supporting evidence, or null>"}}"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_support(text: str) -> Support:
    match = _JSON_RE.search(text)
    if match is None:
        raise ValueError("no JSON object in assessor response")
    data = json.loads(match.group(0))
    raw_id = data.get("citation_id")
    citation_id = str(raw_id) if raw_id not in (None, "null", "") else None
    return Support(score=float(data.get("score", 0.0)), citation_id=citation_id)


class ClaudeSupportAssessor:
    """Independent support assessor backed by Claude. Lazy client.

    Use a DIFFERENT model/tier than the author so it doesn't share blind spots. An
    unparseable response is treated conservatively as unsupported (no invented support).
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._client: object | None = None

    async def assess(self, claim_text: str, evidence: list[Evidence]) -> Support:
        if not evidence:
            return Support(score=0.0, citation_id=None)

        if self._client is None:
            self._client = build_anthropic_chat_model(self._model_name)

        prompt = _PROMPT.format(claim=claim_text, evidence=render_evidence(evidence))
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content if isinstance(message.content, str) else str(message.content)
        try:
            return _parse_support(content)
        except (ValueError, KeyError, json.JSONDecodeError):
            logger.warning("support_assessor_unparseable", claim=claim_text[:80])
            return Support(score=0.0, citation_id=None)
