import json
import re

from .lesson_draft import LessonDraft, SegmentDraft

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_PHASES = ("activate", "demonstrate", "apply", "integrate")


def _segment(raw: dict) -> SegmentDraft:
    return SegmentDraft(
        prose=str(raw.get("prose", "")),
        claims=[str(c) for c in raw.get("claims", []) if str(c).strip()],
    )


def parse_lesson(text: str) -> LessonDraft:
    """Parse the author's JSON into a ``LessonDraft``.

    Requires all four Merrill phases — a lesson cannot exist without them (the schema
    makes a partial lesson unrepresentable; we enforce the same at parse time).
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        raise ValueError("no JSON object in module-author response")
    data = json.loads(match.group(0))

    missing = [p for p in _PHASES if p not in data]
    if missing:
        raise ValueError(f"lesson is missing Merrill phase(s): {missing}")

    return LessonDraft(
        activate=_segment(data["activate"]),
        demonstrate=_segment(data["demonstrate"]),
        apply=_segment(data["apply"]),
        integrate=_segment(data["integrate"]),
    )
