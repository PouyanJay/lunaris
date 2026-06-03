from collections.abc import Sequence

from lunaris_grounding import ExtractedContent
from lunaris_runtime.schema import CourseBrief

# Bound each source excerpt so a few long pages can't blow the prompt budget.
_SOURCE_CLIP_CHARS = 3000

_PROMPT = """You are grounding a course's target in the REAL requirements of its standard.

Target goal: "{goal}"
Subject: "{subject}"
Target level: {level}

Below are excerpts from authoritative sources. Using ONLY what they state (do not invent
requirements they do not support), extract:
  - competencies: the specific competency descriptors that DEFINE reaching this target at this level
    — what a learner must be able to DO — as short phrases. Exclude foundational basics beneath the
    level.
  - score_table: any concrete score/threshold lines the sources give (e.g. "CELPIP 10",
    "IELTS 8.5"), each as a short string. Empty if the sources give none.

Sources:
{sources}

Respond with ONLY this JSON, no prose:
{{"competencies": ["..."], "score_table": ["..."]}}"""


def build_research_prompt(brief: CourseBrief, contents: Sequence[ExtractedContent]) -> str:
    """The distillation prompt: the brief + clipped, URL-headed source excerpts → competencies.

    Each excerpt is clipped (bounded prompt) and headed by its URL so the model distils from the
    fetched text rather than its memory — keeping the targets grounded and traceable to a source.
    """
    sources = "\n\n".join(
        f"--- SOURCE: {content.url} ---\n{content.text[:_SOURCE_CLIP_CHARS]}"
        for content in contents
    )
    return _PROMPT.format(
        goal=brief.goal, subject=brief.subject, level=brief.target_level.value, sources=sources
    )
