import re

from ..json_tolerant import loads_tolerant
from .lesson_draft import LessonDraft, SegmentDraft

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_PHASES = ("activate", "demonstrate", "apply", "integrate")


def _segment(raw: dict) -> SegmentDraft:
    return SegmentDraft(
        prose=str(raw.get("prose", "")),
        claims=[str(c) for c in raw.get("claims", []) if str(c).strip()],
    )


def _str_list(raw: object) -> list[str]:
    """The arc bookends (expects / self_check) as a clean list of non-empty lines, tolerant of a
    missing field (legacy / novice author) or a single string emitted instead of a list."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def parse_lesson(text: str) -> LessonDraft:
    """Parse the author's JSON into a ``LessonDraft``.

    Requires all four Merrill phases — a lesson cannot exist without them (the schema
    makes a partial lesson unrepresentable; we enforce the same at parse time). The arc bookends
    (``expects`` / ``self_check``, P7.3) are optional: absent on the legacy/novice path → empty.
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        raise ValueError("no JSON object in module-author response")
    data = loads_tolerant(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("module-author response is not a JSON object")

    missing = [p for p in _PHASES if p not in data]
    if missing:
        raise ValueError(f"lesson is missing Merrill phase(s): {missing}")

    return LessonDraft(
        activate=_segment(data["activate"]),
        demonstrate=_segment(data["demonstrate"]),
        apply=_segment(data["apply"]),
        integrate=_segment(data["integrate"]),
        expects=_str_list(data.get("expects")),
        self_check=_str_list(data.get("self_check")),
    )
