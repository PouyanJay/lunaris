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
- Every objective gets at least one assessment item. Each item has a "prompt" (the summative
  check that proves the objective) AND a "pass_criterion": the explicit, concrete, GRADEABLE bar
  a passing response must clear (e.g. "Names >=2 AZs and a failover path; no single point of
  failure"), NOT a vague "does it look right". The lesson will be authored backward from this bar.
- Keep modules in the given order; do not move a KC before its prerequisites.
- In "kcs" and "kc" fields, copy the kc id exactly as written in the teaching order
  (the id string before the dash) — never the list number."""

# Appended when research grounded the target's real competency framework (P7.2; CQ Phase 1.3
# presents the structured AREAS): the modules are designed backward from the actual standard, each
# area/competency covered by a module's objectives, and the mapping is recorded structurally (P7.3)
# — each module tagged with the ONE competency it builds.
_COMPETENCY_MAPPING = """
- Map the modules to this researched competency framework of the target — each area's competencies
  must be covered by at least one module's objectives (backward design from the real standard).
  Tag each module with the ONE competency it primarily builds, verbatim from the framework, in a
  "competency" field:
{framework}"""

# The base response shape. The ``<competency>`` sentinel (a non-JSON token, so the braces stay
# normal + readable) is replaced with the per-module competency line only when research grounded the
# competencies — else with "" (so the model is never asked to invent a competency tag).
_JSON_SHAPE = """

Respond with ONLY this JSON, no prose:
{"modules": [{"title": "...", <competency>"kcs": ["kc_id", ...], "objectives": [
  {"kc": "kc_id", "statement": "Given ..., the learner can ...",
    "bloom_level": "apply",
    "items": [{"prompt": "...", "pass_criterion": "..."}]}]}]}"""

_COMPETENCY_SENTINEL = "<competency>"
_COMPETENCY_FIELD = '"competency": "...", '


def build_curriculum_prompt(graph: PrerequisiteGraph, brief: CourseBrief | None = None) -> str:
    """The backward-design prompt: group the ordered KCs into modules with measurable objectives.

    When the brief carries researched competencies (P7.2/P7.3), the architect is also told to map
    modules to those competencies AND to tag each module with the one it builds (a structural
    ``competency`` field), so the curriculum is designed backward from the real standard, not a
    generic difficulty climb. Without research it is the plain backward-design prompt.
    """
    labels = {kc.id: kc.label for kc in graph.nodes}
    ordered = "\n".join(
        f"{i + 1}. {kc_id} — {labels.get(kc_id, kc_id)}" for i, kc_id in enumerate(graph.topo_order)
    )
    prompt = _HEADER.format(ordered_kcs=ordered)
    research = brief.research if brief is not None else None
    grounded = bool(research and research.competencies)
    if grounded:
        prompt += _COMPETENCY_MAPPING.format(framework=research.grounding_outline())
    competency_field = _COMPETENCY_FIELD if grounded else ""
    return prompt + _JSON_SHAPE.replace(_COMPETENCY_SENTINEL, competency_field)
