"""Parse the coverage judge's JSON verdict into typed gaps (CQ Phase 4.2).

Tolerant like the other agent parsers (the model occasionally fences or comma-slips its JSON). Two
guards make the gate trustworthy: a gap is kept only when its competency is one that was actually
promised (the judge can't invent a gap), and an unparseable reply returns ``None`` so the caller
falls back to the deterministic check rather than treating garbage as "all clear".
"""

import re

from ..subagents.json_tolerant import loads_tolerant
from .report import CoverageGap

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_coverage_gaps(text: str, promised: set[str]) -> list[CoverageGap] | None:
    """Read the judge's ``{"gaps": [...]}`` reply, keeping only gaps for promised competencies.

    Returns the parsed gaps (possibly empty == every competency built), or ``None`` when the reply
    has no JSON object / isn't a dict — the signal for the caller to fall back to the deterministic
    check. A gap whose competency was not promised is dropped (the judge can only flag real ones).
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        return None
    data = loads_tolerant(match.group(0))
    if not isinstance(data, dict):
        return None
    gaps: list[CoverageGap] = []
    for raw in data.get("gaps", []):
        if not isinstance(raw, dict):
            continue
        competency = str(raw.get("competency", "")).strip()
        if competency in promised:
            gaps.append(CoverageGap(competency, str(raw.get("reason", "")).strip()))
    return gaps
