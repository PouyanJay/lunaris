from collections.abc import Sequence

from lunaris_runtime.schema import Module

from .candidate_view import CandidateView

_HEADER = """You are vetting external learning resources for one lesson of a course.

Lesson module: "{title}"
{competency_line}Learning objectives:
{objectives}

Candidate resources (already found by search):
{candidates}"""

_INSTRUCTION = """Judge each candidate on its CONTENT (the description/snippet + what a good result
looks like) and its LEVEL — NOT its title, which may be clickbait that only sounds on-topic. Select
ONLY the candidates that genuinely help a learner reach this lesson's competency at the right
level — drop anything off-topic, too basic, too advanced, or low-quality. For each one you keep,
decide which teaching phase it best supports:
- activate: hooks interest / connects to prior knowledge
- demonstrate: explains the strategy or shows a worked example
- apply: lets the learner practise
- integrate: helps transfer to their own context

For each kept candidate give its index, the phase, a one-line "why this helps" tied to the
competency, and a credibility score from 0.0 (weak) to 1.0 (excellent). Keep at most {limit}. If
none clear the bar, return an empty list.

Respond with ONLY this JSON, no prose:
{{"selected": [{{"index": 0, "phase": "demonstrate", "why": "...", "credibility": 0.8}}]}}"""


def _render_candidate(candidate: CandidateView) -> str:
    """One candidate as a multi-line block: identity + the CONTENT/level signals, never the tier."""
    lines = [f"{candidate.index}. [{candidate.kind.value}] {candidate.title} — {candidate.source}"]
    if candidate.good_result_looks_like:
        lines.append(f"   what a good result looks like: {candidate.good_result_looks_like}")
    if candidate.snippet:
        lines.append(f"   content: {candidate.snippet}")
    if candidate.level_hint:
        lines.append(f"   target level: {candidate.level_hint}")
    lines.append(f"   {candidate.url}")
    return "\n".join(lines)


def build_curation_prompt(
    module: Module, candidates: Sequence[CandidateView], *, limit: int
) -> str:
    """The relevance-judge prompt: pick + place the best candidates, blind to the trust tier (§15).

    The judge sees each candidate's kind / title / source host / URL plus its CONTENT signals (the
    snippet, what a good result looks like, the target level) — but never our classified tier — and
    selects the ones that fit the lesson's competency at the right level, assigning a phase, a
    "why", and a credibility score. ``limit`` caps how many it may keep (the per-lesson budget).
    """
    competency_line = f"Target competency: {module.competency}\n" if module.competency else ""
    objectives = (
        "\n".join(f"- {objective.statement}" for objective in module.objectives) or "- (none)"
    )
    listed = "\n".join(_render_candidate(c) for c in candidates)
    header = _HEADER.format(
        title=module.title,
        competency_line=competency_line,
        objectives=objectives,
        candidates=listed,
    )
    return f"{header}\n\n{_INSTRUCTION.format(limit=limit)}"
