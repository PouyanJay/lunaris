"""The facts-immutable guarantee for the scope-band polish step (CQ Phase 3.1).

A polished band is accepted only where it cannot have invented or dropped a fact: the effort is
always the deterministic original, and a rewritten delivers/excludes list is taken only when it has
the SAME number of lines and no blank line (a count change is an invented or dropped promise; a
blank line is a lost one). Pure; the Claude polisher applies it so even a drifting model degrades to
the deterministic band rather than misrepresenting the course.
"""

from lunaris_runtime.schema import CourseScope


def _accept_lines(candidate: list[str], original: list[str]) -> list[str]:
    """The candidate lines iff same-count and all non-blank; otherwise the original lines."""
    if len(candidate) != len(original):
        return original
    stripped = [line.strip() for line in candidate]
    if any(not line for line in stripped):
        return original
    return stripped


def reconcile_scope(original: CourseScope, candidate: CourseScope) -> CourseScope:
    """Merge a polished ``candidate`` onto the deterministic ``original``, keeping the facts.

    The effort band is a numeric fact and is never taken from the candidate. Each line list is taken
    from the candidate only when it preserves the original's line count and carries no blank line.
    """
    return CourseScope(
        effort=original.effort,
        delivers=_accept_lines(candidate.delivers, original.delivers),
        excludes=_accept_lines(candidate.excludes, original.excludes),
    )
