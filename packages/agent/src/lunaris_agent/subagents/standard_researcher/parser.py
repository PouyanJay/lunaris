import re

from lunaris_runtime.schema import CompetencyArea

from ..json_tolerant import loads_tolerant
from .distillation import Distillation

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _string_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [stripped for item in raw if (stripped := str(item).strip())]


def _competency_areas(raw: object) -> list[CompetencyArea]:
    if not isinstance(raw, list):
        return []
    areas: list[CompetencyArea] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        competencies = _string_list(item.get("competencies"))
        name = str(item.get("name", "")).strip()
        # Keep a name-only area (no descriptors yet) so the structure stage can still see a skeleton
        # area from a thin source; drop only the truly empty object.
        if name or competencies:
            areas.append(CompetencyArea(name=name, competencies=competencies))
    return areas


def parse_distillation(text: str) -> Distillation:
    """Parse a distillation round into a structured ``Distillation`` (CQ Phase 1.1), tolerant of
    prose/fences and of the older flat shape.

    Reads the structured ``areas`` framework when present (flattening it into ``competencies`` for
    the flat consumers); falls back to a flat ``competencies`` list when no areas were returned.
    Best-effort: a missing/malformed response degrades to an empty distillation rather than raising.
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        return Distillation()
    data = loads_tolerant(match.group(0))
    if not isinstance(data, dict):
        return Distillation()
    areas = _competency_areas(data.get("areas"))
    competencies = (
        CompetencyArea.flatten(areas) if areas else _string_list(data.get("competencies"))
    )
    return Distillation(
        areas=areas,
        competencies=competencies,
        score_table=_string_list(data.get("score_table")),
        follow_up_queries=_string_list(data.get("follow_up_queries")),
    )


def parse_research(text: str) -> tuple[list[str], list[str]]:
    """Parse the distillation JSON into ``(competencies, score_table)``, tolerant of prose/fences.

    Retained for the flat callers; new code uses :func:`parse_distillation`. Research is
    best-effort, so a missing or malformed response degrades to empty lists rather than raising — an
    empty distillation marks the research PARTIAL, it never crashes the build.
    """
    distillation = parse_distillation(text)
    return distillation.competencies, distillation.score_table
