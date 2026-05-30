import json
import re

from lunaris_runtime.schema import BloomLevel, KnowledgeComponent

from .extraction import Extraction

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
    data = json.loads(match.group(0))

    raw_kcs = data.get("kcs", [])
    if not raw_kcs:
        raise ValueError("extractor returned no knowledge components")

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
    ]

    ids = {kc.id for kc in kcs}
    goal_id = str(data.get("goal_id", "")) or kcs[-1].id
    if goal_id not in ids:
        raise ValueError(f"goal_id {goal_id!r} is not among the extracted KCs")

    return Extraction(kcs=kcs, goal_id=goal_id)
