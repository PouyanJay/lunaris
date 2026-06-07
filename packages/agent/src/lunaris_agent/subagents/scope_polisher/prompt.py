"""The prompt for the scope-band wording polish (CQ Phase 3.1).

Hands the model the deterministic band plus light brief context and asks it to rewrite ONLY the
wording of the delivers/excludes lines — same number of lines, same meaning, the same specific names
and numbers — returning a strict JSON object. The estimator already guarantees the facts; this is a
copy pass, and ``reconcile_scope`` enforces the constraints regardless of what the model returns.
"""

import json

from lunaris_runtime.schema import CourseBrief, CourseScope


def _context_line(brief: CourseBrief | None) -> str:
    """A short brief context so the rewrite matches the learner's framing; empty with no brief."""
    if brief is None:
        return ""
    bits = [
        f"subject: {brief.subject}",
        f"goal: {brief.goal}",
        f"goal type: {brief.goal_type.value}",
    ]
    return "For context, the course is — " + "; ".join(bits) + ".\n\n"


def build_polish_prompt(scope: CourseScope, brief: CourseBrief | None) -> str:
    """Build the polish instruction for a scope band. Returns a single prompt string."""
    payload = json.dumps({"delivers": scope.delivers, "excludes": scope.excludes}, indent=2)
    return (
        "You are refining the wording of a course's honest scope summary — the lines that tell a "
        "learner what the course does and does not get them.\n\n"
        f"{_context_line(brief)}"
        "Rewrite each line below to be clearer, warmer, and more concrete, but obey these rules "
        "exactly:\n"
        "- Keep the SAME number of lines in each list. Do not add or remove a line.\n"
        "- Preserve each line's meaning and any specific names, standards, or numbers.\n"
        "- Never promise more than the original line does. The excludes are honest limits — keep "
        "them honest.\n"
        "- Do not mention effort, time, or hours; that is handled elsewhere.\n\n"
        f"Lines to rewrite:\n{payload}\n\n"
        'Return ONLY a JSON object of the same shape: {"delivers": [...], "excludes": [...]}.'
    )
