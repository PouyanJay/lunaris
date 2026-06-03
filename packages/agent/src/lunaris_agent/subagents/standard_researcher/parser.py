import re

from ..json_tolerant import loads_tolerant

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _string_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [stripped for item in raw if (stripped := str(item).strip())]


def parse_research(text: str) -> tuple[list[str], list[str]]:
    """Parse the distillation JSON into ``(competencies, score_table)``, tolerant of prose/fences.

    Research is best-effort, so — unlike the brief/concept parsers — a missing or malformed response
    degrades to empty lists rather than raising: an empty distillation marks the research PARTIAL,
    it never crashes the build.
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        return [], []
    data = loads_tolerant(match.group(0))
    if not isinstance(data, dict):
        return [], []
    return _string_list(data.get("competencies")), _string_list(data.get("score_table"))
