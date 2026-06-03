from lunaris_runtime.schema import CourseBrief, PrerequisiteGraph

_HEADER = """You are a curriculum architect applying BACKWARD DESIGN.

You are given knowledge components (KCs) in their validated teaching order. Group
adjacent KCs into coherent modules, and for EACH KC write one measurable learning
objective and the assessment items that will prove it — BEFORE any lesson content.

Teaching order (earliest first):
{ordered_kcs}

Rules:
- Every KC gets exactly one objective. Phrase it "Given <context>, the learner can
  <verb> ...", using a verb that matches its Bloom level (remember, understand,
  apply, analyze, evaluate, create).
- Every objective gets at least one assessment item prompt that measures it.
- Keep modules in the given order; do not move a KC before its prerequisites."""

# Appended when research grounded the target's real competencies (P7.2): the modules are designed
# backward from the actual standard, each competency covered by at least one module's objectives.
_COMPETENCY_MAPPING = """
- Map the modules to these researched competencies of the target — each should be covered by at
  least one module's objectives (backward design from the real standard):
{competencies}"""

_JSON_SHAPE = """

Respond with ONLY this JSON, no prose:
{"modules": [{"title": "...", "kcs": ["kc_id", ...], "objectives": [
  {"kc": "kc_id", "statement": "Given ..., the learner can ...",
    "bloom_level": "apply", "item_prompts": ["..."]}]}]}"""


def build_curriculum_prompt(graph: PrerequisiteGraph, brief: CourseBrief | None = None) -> str:
    """The backward-design prompt: group the ordered KCs into modules with measurable objectives.

    When the brief carries researched competencies (P7.2), the architect is additionally told to map
    the modules to those competencies, so the curriculum is designed backward from the real standard
    rather than a generic difficulty climb. Without research it is the plain backward-design prompt.
    """
    labels = {kc.id: kc.label for kc in graph.nodes}
    ordered = "\n".join(
        f"{i + 1}. {kc_id} — {labels.get(kc_id, kc_id)}" for i, kc_id in enumerate(graph.topo_order)
    )
    prompt = _HEADER.format(ordered_kcs=ordered)
    competencies = brief.research.competencies if brief is not None and brief.research else []
    if competencies:
        bullets = "\n".join(f"- {competency}" for competency in competencies)
        prompt += _COMPETENCY_MAPPING.format(competencies=bullets)
    return prompt + _JSON_SHAPE
