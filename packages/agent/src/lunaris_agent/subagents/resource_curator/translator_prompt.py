import json

from lunaris_runtime.schema import CourseBrief, Modality, Module

_SYSTEM = """You convert ONE learning competency into 1-4 web search queries that will surface \
genuinely useful learning resources, BEFORE anything reaches a search API.

THE PROBLEM YOU SOLVE
Competencies are written in curriculum/institutional language (e.g. "Comprehend complex information
from diverse sources"). Creators do not TITLE resources that way and learners do not SEARCH that
way. Passing the competency through verbatim, or with a constant suffix like "video tutorial",
returns junk or nothing — and fails hardest on the most abstract competencies. Rewrite the
competency into the natural search vernacular of its domain and platform.

RULES
1. NEVER reuse the competency's wording verbatim. Rewrite into phrasing a knowledgeable person would
   actually type into a search box.
2. Choose the query SHAPE from goal_type + modality + the resource kind needed. Do NOT append
   "video tutorial" by default:
   - goal_type knowledge → explainers/overviews/lectures/documentaries ("<topic> explained").
   - goal_type skill → how-to/tutorial/step-by-step/drills/practice for the actual skill.
   - goal_type credential → use the exam's REAL name + task + artifact
     ("<exam> <task> strategies / sample high-scoring response / rubric"); favor the official maker.
   - goal_type behavior → habit/protocol/routine framing, not a one-off lecture.
   - modality receptive → seek INPUT MATERIAL to practise ON (a lecture/talk/podcast/text),
     NOT a lesson ABOUT it; optionally one strategy explainer to accompany it.
   - modality productive → mix a concept explainer WITH practice/shadowing/examples to make output.
   - modality procedural → step-by-step demonstrations + follow-along practice.
   - modality conceptual → explainers that build the idea + relations, with worked examples.
3. Bake the LEVEL into the words natively ("C1", "advanced", "for practitioners"), matched to
   target_level. Do not rely on generic suffixes.
4. DIVERSIFY. The queries must cover DIFFERENT angles or resource kinds so the candidate pool is
   varied — never paraphrases of one query.
5. Search by FUNCTION, never by hype. Never use "best", "top", "ultimate", or a bare year.
6. When a domain has an authoritative primary source (e.g. the official test maker), favor a query
   likely to surface it.
7. If `feedback` says a prior attempt returned nothing: BROADEN. Drop domain jargon, go one level
   more general, use the single most common layperson phrasing.

OUTPUT CONTRACT
Return ONLY a JSON array (no prose, no fences) of 1-4 objects, ordered by expected usefulness:
{ "query": str,
  "kind": one of ["video","article","practice","docs"],   // where to look / what kind of resource
  "media_role": ["input_material","concept_explainer","worked_example","practice","reference"],
  "level_hint": str or null,
  "good_result_looks_like": str,   // <= 20 words: the signal for the downstream content judge
  "rationale": str }               // <= 20 words"""


def build_translator_prompt(
    module: Module,
    brief: CourseBrief | None,
    modality: Modality | None,
    feedback: str | None,
) -> str:
    """The query-translator prompt: one competency → diverse, domain-vernacular search queries.

    Carries the shaping inputs the model derives query SHAPE from — the course ``goal_type`` and
    ``target_level`` (from the brief) plus the module's representative ``modality`` — and the
    ``feedback`` for the broaden-on-empty retry. The competency is to rewrite, not to emit verbatim.
    """
    competency = module.competency or module.title
    payload = {
        "competency": competency,
        "domain": brief.subject if brief is not None else "",
        "goal_type": brief.goal_type.value if brief is not None else None,
        "target_level": brief.target_level.value if brief is not None else None,
        "modality": modality.value if modality is not None else None,
        "feedback": feedback,
    }
    return f"{_SYSTEM}\n\nInput:\n{json.dumps(payload, ensure_ascii=False)}"
