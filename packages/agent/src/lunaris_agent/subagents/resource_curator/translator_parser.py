import re

from lunaris_runtime.schema import ResourceKind

from ..json_tolerant import loads_tolerant
from .search_query import SearchQuery

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
_HYPE_RE = re.compile(r"\b(best|top|ultimate)\b", re.IGNORECASE)
# Resource kinds the translator may target (and the curator can route): VIDEO → the IVideoSource,
# the rest → the shared search. Anything else (tool/reference) falls back to a safe default.
_ROUTABLE_KINDS = {
    "video": ResourceKind.VIDEO,
    "article": ResourceKind.ARTICLE,
    "practice": ResourceKind.PRACTICE,
    "docs": ResourceKind.DOCS,
}
_DEFAULT_KIND = ResourceKind.ARTICLE


def _coerce_kind(value: object) -> ResourceKind:
    return _ROUTABLE_KINDS.get(str(value).strip().lower(), _DEFAULT_KIND)


def _clean_query(query: str) -> str:
    """Strip hype words (rule 5) and collapse the whitespace they leave behind."""
    return re.sub(r"\s{2,}", " ", _HYPE_RE.sub("", query)).strip()


def _extract_entries(text: str) -> list[object]:
    """Pull the JSON array out of the model output; empty on prose / malformed / non-array."""
    match = _JSON_ARRAY_RE.search(text)
    if match is None:
        return []
    try:
        data = loads_tolerant(match.group(0))
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def parse_search_queries(text: str, *, competency: str) -> list[SearchQuery]:
    """Parse the translator's JSON array into ``SearchQuery``s, enforcing the rules in code (P2/T1).

    Best-effort like the rest of curation: prose / malformed output yields an empty list (the caller
    then uses the deterministic fallback), never a raise. Two rules the prompt asks for are enforced
    here too, not just trusted to the model: a query equal to the competency verbatim is DROPPED
    (rule 1), and hype words are stripped (rule 5). An entry without a usable query is skipped.
    """
    normalized_competency = competency.strip().lower()
    queries: list[SearchQuery] = []
    for raw in _extract_entries(text):
        if not isinstance(raw, dict):
            continue
        query = _clean_query(str(raw.get("query", "")))
        if not query or query.lower() == normalized_competency:
            continue
        queries.append(
            SearchQuery(
                kind=_coerce_kind(raw.get("kind")),
                query=query,
                media_role=str(raw.get("media_role", "")).strip(),
                level_hint=str(raw.get("level_hint") or "").strip(),
                good_result_looks_like=str(raw.get("good_result_looks_like", "")).strip(),
                rationale=str(raw.get("rationale", "")).strip(),
            )
        )
    return queries
