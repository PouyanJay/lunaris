import re

import structlog
from lunaris_runtime.schema import BloomLevel, KnowledgeComponent

from ..json_tolerant import loads_tolerant
from .extraction import Extraction

logger = structlog.get_logger()

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _coerce_bloom(value: object) -> BloomLevel:
    try:
        return BloomLevel(str(value).lower())
    except ValueError:
        return BloomLevel.APPLY


def _clamp(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.5


def parse_extraction(text: str) -> Extraction:
    """Parse the model's JSON into a validated ``Extraction``.

    Tolerant of prose/code-fences around the JSON; strict about the result being a
    usable KC set with a goal that exists among the KCs.
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        raise ValueError("no JSON object in extractor response")
    data = loads_tolerant(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("extractor response is not a JSON object")

    raw_kcs = data.get("kcs", [])
    if not raw_kcs:
        raise ValueError("extractor returned no knowledge components")

    # Skip any malformed entry (a non-dict, or one missing its id) rather than KeyError on it — a
    # repaired-but-truncated response can leave a half-written KC. A usable KC needs an id.
    kcs = [
        KnowledgeComponent(
            id=str(item["id"]),
            label=str(item.get("label", item["id"])),
            definition=str(item.get("definition", "")),
            difficulty=_clamp(item.get("difficulty", 0.5)),
            bloom_ceiling=_coerce_bloom(item.get("bloom_ceiling")),
            sources=[str(s) for s in item.get("sources", [])],
        )
        for item in raw_kcs
        if isinstance(item, dict) and item.get("id")
    ]
    if not kcs:
        raise ValueError("extractor returned no usable knowledge components")

    ids = {kc.id for kc in kcs}
    goal_id = str(data.get("goal_id", "")) or kcs[-1].id
    if goal_id not in ids:
        # The live model occasionally names a goal that isn't among the KCs it extracted (common on
        # fuzzy, non-technical topics). Snap to the last KC — the hardest, the conventional goal —
        # rather than crash the whole build; the prereq-graph moat still orders the KCs we have.
        logger.warning("extractor_goal_id_not_in_kcs", goal_id=goal_id, fallback=kcs[-1].id)
        goal_id = kcs[-1].id

    return Extraction(kcs=kcs, goal_id=goal_id)
