import re

import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_runtime.resilience import (
    build_chat_model,
    retry_on_rate_limit,
)

from ...subagents.json_tolerant import loads_tolerant
from .relevance_judge import RelevanceVerdict

logger = structlog.get_logger()

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_MAX_TEXT_CHARS = 4000  # one page's lede is enough to judge topicality; bounds the prompt's tokens
_PROMPT = (
    "You are vetting whether a web page can serve as teaching evidence for ONE concept. Judge only "
    "whether the text is genuinely about this concept — NOT its quality, source, or trust "
    "(another system handles trust). Answer with a JSON object and nothing else:\n"
    '{{"relevant": true|false, "reason": "<one short clause>"}}\n\n'
    "Concept: {label}\n"
    "What it means: {definition}\n\n"
    "Page text:\n{text}"
)


def _parse(raw: str) -> RelevanceVerdict:
    """Parse the judge's JSON verdict, tolerant of prose/fences; default to relevant if unreadable.

    Permissive on a parse miss (the contract): an unreadable verdict means "keep it and let the
    verifier's trust floor decide", never a silent drop of possibly-good evidence.
    """
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        return RelevanceVerdict(True, "unparseable judge response — kept for the verifier")
    data = loads_tolerant(match.group(0))
    if not isinstance(data, dict) or not isinstance(data.get("relevant"), bool):
        return RelevanceVerdict(True, "unparseable judge response — kept for the verifier")
    reason = data.get("reason")
    return RelevanceVerdict(data["relevant"], reason if isinstance(reason, str) else "")


class ClaudeRelevanceJudge:
    """The live relevance judge (worker tier), blind to the source's trust label by construction.

    Its prompt carries only the concept (label + definition) and the extracted page text — never the
    URL, domain, or trust tier — so its on-topic verdict cannot be biased by provenance. One light
    call per fetched source. Best-effort: a transport/parse failure returns a permissive verdict, so
    discovery never drops evidence on an outage — the verifier's trust floor remains the real gate.

    ``model`` is a model id (lazy ``ChatAnthropic``) or an injected chat model (tests).
    """

    def __init__(self, model: str | BaseChatModel) -> None:
        self._model = model
        self._client: BaseChatModel | None = None

    async def is_relevant(
        self, *, kc_label: str, kc_definition: str, text: str
    ) -> RelevanceVerdict:
        prompt = _PROMPT.format(
            label=kc_label, definition=kc_definition, text=text[:_MAX_TEXT_CHARS]
        )
        try:
            message = await retry_on_rate_limit(lambda: self._chat_model().ainvoke(prompt))
        except Exception:
            logger.warning("relevance_judge_failed", kc_label=kc_label, exc_info=True)
            return RelevanceVerdict(True, "judge unavailable — kept for the verifier")
        raw = message.content if isinstance(message.content, str) else str(message.content)
        return _parse(raw)

    def _chat_model(self) -> BaseChatModel:
        if not isinstance(self._model, str):
            return self._model
        if self._client is None:
            self._client = build_chat_model(self._model)
        return self._client
