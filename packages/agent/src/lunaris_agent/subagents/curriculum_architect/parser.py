import re

from lunaris_runtime.schema import BloomLevel

from ..json_tolerant import loads_tolerant
from .plan import AssessmentItemPlan, CurriculumPlan, ModulePlan, ObjectivePlan

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_BLOOM_VERBS: dict[BloomLevel, tuple[str, ...]] = {
    BloomLevel.REMEMBER: ("define", "list", "recall", "name", "identify", "state"),
    BloomLevel.UNDERSTAND: ("explain", "describe", "summarize", "classify", "compare", "interpret"),
    BloomLevel.APPLY: ("apply", "use", "implement", "solve", "compute", "demonstrate"),
    BloomLevel.ANALYZE: ("analyze", "differentiate", "examine", "contrast", "deconstruct"),
    BloomLevel.EVALUATE: ("evaluate", "justify", "critique", "assess", "argue", "judge"),
    BloomLevel.CREATE: ("create", "design", "construct", "compose", "develop", "formulate"),
}


def _coerce_bloom(value: object) -> BloomLevel:
    try:
        return BloomLevel(str(value).lower())
    except ValueError:
        return BloomLevel.UNDERSTAND


def _optional_str(raw: object) -> str | None:
    """A present, non-blank string value, else ``None`` — for an optional free-text field the model
    may omit, blank, or (mis)emit as a non-string (the module's researched competency)."""
    if not isinstance(raw, str):
        return None
    return raw.strip() or None


def _has_bloom_verb(statement: str, level: BloomLevel) -> bool:
    lowered = statement.lower()
    return any(verb in lowered for verb in _BLOOM_VERBS[level])


def _parse_items(obj: dict) -> list[AssessmentItemPlan]:
    """Read an objective's assessment items (CQ Phase 4.1: prompt + gradeable pass criterion).

    Accepts the structured shape ``items: [{prompt, pass_criterion}]``; falls back to the legacy
    ``item_prompts: ["..."]`` (bare strings → empty criterion) so a pre-P4 response still parses.
    Blank prompts are skipped. A structured item may also be a bare string (a tolerant slip). A
    non-list ``items`` (e.g. the model emitted a bare string) is ignored, not character-iterated.
    """
    raw_items = obj.get("items", [])
    items: list[AssessmentItemPlan] = []
    for raw in raw_items if isinstance(raw_items, list) else []:
        if isinstance(raw, dict):
            prompt = str(raw.get("prompt", "")).strip()
            if prompt:
                items.append(AssessmentItemPlan(prompt, str(raw.get("pass_criterion", "")).strip()))
        elif stripped := str(raw).strip():
            items.append(AssessmentItemPlan(stripped))
    if not items:
        legacy = obj.get("item_prompts", [])
        items = [
            AssessmentItemPlan(stripped)
            for p in (legacy if isinstance(legacy, list) else [])
            if (stripped := str(p).strip())
        ]
    return items


def parse_curriculum(text: str, known_kc_ids: set[str]) -> CurriculumPlan:
    """Parse the architect's JSON into a validated ``CurriculumPlan``.

    Enforces the backward-design invariants structurally: every objective targets a
    real KC, names a valid Bloom level, and carries at least one assessment item.
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        raise ValueError("no JSON object in architect response")
    data = loads_tolerant(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("architect response is not a JSON object")

    raw_modules = data.get("modules", [])
    if not raw_modules:
        raise ValueError("architect returned no modules")

    modules: list[ModulePlan] = []
    seen_kcs: set[str] = set()
    for raw in raw_modules:
        objectives: list[ObjectivePlan] = []
        for obj in raw.get("objectives", []):
            if not isinstance(obj, dict) or "kc" not in obj:
                continue  # skip a malformed/half-written objective rather than KeyError on it
            kc = str(obj["kc"])
            if kc not in known_kc_ids:
                raise ValueError(f"objective targets unknown KC {kc!r}")
            items = _parse_items(obj)
            if not items:
                raise ValueError(f"objective for KC {kc!r} has no assessment items")
            objectives.append(
                ObjectivePlan(
                    kc=kc,
                    statement=str(obj.get("statement", "")),
                    bloom_level=_coerce_bloom(obj.get("bloom_level")),
                    items=items,
                )
            )
            seen_kcs.add(kc)
        if not objectives:
            raise ValueError("module has no objectives")
        modules.append(
            ModulePlan(
                title=str(raw.get("title", "Module")),
                kcs=[str(k) for k in raw.get("kcs", [])],
                objectives=objectives,
                # The researched target skill the architect mapped this module to (P7.3); None on
                # the no-research path (absent / blank / non-string).
                competency=_optional_str(raw.get("competency")),
            )
        )

    return CurriculumPlan(modules=modules)


def objective_has_valid_bloom_verb(statement: str, level: BloomLevel) -> bool:
    """Public helper: does the statement contain a verb appropriate to its Bloom level?"""
    return _has_bloom_verb(statement, level)
