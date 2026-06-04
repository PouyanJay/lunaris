import re
from dataclasses import dataclass

from ..json_tolerant import loads_tolerant

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_PHASES = frozenset({"activate", "demonstrate", "apply", "integrate"})
_DEFAULT_PHASE = "demonstrate"


@dataclass(frozen=True)
class CurationChoice:
    """One judge decision: keep candidate ``index`` on ``phase`` with a ``why`` + credibility."""

    index: int
    phase: str
    why: str
    credibility: float


def _coerce_phase(value: object) -> str:
    phase = str(value).strip().lower()
    return phase if phase in _PHASES else _DEFAULT_PHASE


def _coerce_credibility(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))  # clamp to 0..1; a wild score never escapes
    except (TypeError, ValueError):
        return 0.0


def parse_curation(text: str) -> list[CurationChoice]:
    """Parse the judge's JSON into selected candidates, tolerant of prose/fences (P7.4).

    Curation is best-effort, so a missing/malformed response degrades to an empty list (no resources
    attached) rather than raising — it never crashes the build. An entry without a usable integer
    ``index`` is skipped; ``phase`` falls back to demonstrate; ``credibility`` is clamped to 0..1.
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        return []
    data = loads_tolerant(match.group(0))
    if not isinstance(data, dict):
        return []
    choices: list[CurationChoice] = []
    for raw in data.get("selected", []):
        if not isinstance(raw, dict) or "index" not in raw:
            continue
        try:
            index = int(raw["index"])
        except (TypeError, ValueError):
            continue
        choices.append(
            CurationChoice(
                index=index,
                phase=_coerce_phase(raw.get("phase")),
                why=str(raw.get("why", "")).strip(),
                credibility=_coerce_credibility(raw.get("credibility")),
            )
        )
    return choices
