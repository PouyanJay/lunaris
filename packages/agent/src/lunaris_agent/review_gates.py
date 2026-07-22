"""Build the persisted `ReviewGate` list from finalize's four gate results (course-review-publish).

Finalize runs the structure critic, the coverage critic, the grounding-honesty assessment, and the
authoring triage, then decides `review` vs `published`. Before this it dropped *why* — leaving the
review state unexplained. This turns those four results into a stable, learner-facing `ReviewGate`
list persisted on the course, so the review drawer can show the owner what held it. All four gates
are always emitted (passed ones included) so the drawer shows the full picture, not just the misses.
"""

from lunaris_runtime.schema import ReviewGate, ReviewGateStatus

# How many structure issues / uncovered competencies to name before the phrase rolls up to
# "and N more" — enough to be specific, capped so a gate detail stays one scannable line.
_MAX_ISSUES_LISTED = 3
_MAX_COMPETENCIES_LISTED = 4


def _listed(items: list[str], limit: int, *, sep: str) -> str:
    """Join the first `limit` items, rolling any remainder up to 'and N more'."""
    if len(items) <= limit:
        return sep.join(items)
    return sep.join(items[:limit]) + f"{sep}and {len(items) - limit} more"


def _structure_gate(issues: list[str]) -> ReviewGate:
    if not issues:
        return ReviewGate(
            key="structure",
            label="Structure",
            status=ReviewGateStatus.PASSED,
            detail="No structural issues were found.",
        )
    noun = "issue" if len(issues) == 1 else "issues"
    listed = _listed(issues, _MAX_ISSUES_LISTED, sep="; ")
    return ReviewGate(
        key="structure",
        label="Structure",
        status=ReviewGateStatus.WARNING,
        detail=f"{len(issues)} structural {noun}: {listed}.",
    )


def _coverage_gate(competencies: list[str]) -> ReviewGate:
    if not competencies:
        return ReviewGate(
            key="coverage",
            label="Coverage",
            status=ReviewGateStatus.PASSED,
            detail="Every promised competency is built.",
        )
    noun = "competency" if len(competencies) == 1 else "competencies"
    listed = _listed(competencies, _MAX_COMPETENCIES_LISTED, sep=", ")
    return ReviewGate(
        key="coverage",
        label="Coverage",
        status=ReviewGateStatus.WARNING,
        detail=f"{len(competencies)} promised {noun} not fully built: {listed}.",
    )


def _grounding_gate(caveat: str, needs_review: bool) -> ReviewGate:
    # A disclosed caveat OR a withheld (needs_review) verdict both read as a caveat — the learner
    # still sees it after publish, so it's never a hard block, always an honest note.
    if caveat or needs_review:
        return ReviewGate(
            key="grounding",
            label="Grounding honesty",
            status=ReviewGateStatus.CAVEAT,
            detail=caveat or "A research-needing goal could not be fully grounded in the corpus.",
        )
    return ReviewGate(
        key="grounding",
        label="Grounding honesty",
        status=ReviewGateStatus.PASSED,
        detail="Claims are grounded in the researched standard.",
    )


def _authoring_gate(needs_review: bool) -> ReviewGate:
    if needs_review:
        return ReviewGate(
            key="authoring",
            label="Author confidence",
            status=ReviewGateStatus.WARNING,
            detail="The author → verify loop flagged one or more lessons as low-confidence.",
        )
    return ReviewGate(
        key="authoring",
        label="Author confidence",
        status=ReviewGateStatus.PASSED,
        detail="All lessons cleared the author → verify loop.",
    )


def build_review_gates(
    *,
    issues: list[str],
    authoring_needs_review: bool,
    honesty_caveat: str,
    honesty_needs_review: bool,
    coverage_competencies: list[str],
) -> list[ReviewGate]:
    """Map finalize's four gate results to the persisted `ReviewGate` list, in a stable order.

    `issues` is the structure critic's output; `authoring_needs_review` is the draft's authoring
    triage; `honesty_caveat` / `honesty_needs_review` are the grounding-honesty verdict;
    `coverage_competencies` are the names of any promised competencies not materially built.
    """
    return [
        _structure_gate(issues),
        _coverage_gate(coverage_competencies),
        _grounding_gate(honesty_caveat, honesty_needs_review),
        _authoring_gate(authoring_needs_review),
    ]
