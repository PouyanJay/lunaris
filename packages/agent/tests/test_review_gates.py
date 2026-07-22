"""Unit tests for `build_review_gates` — the pure mapping from finalize's four gate results
(structure / coverage / grounding / authoring) to the persisted `ReviewGate` list the review drawer
reads (course-review-publish T2). No harness: the mapping is exercised in isolation."""

from lunaris_agent.review_gates import FinalizeGateSignals, build_review_gates
from lunaris_runtime.schema import ReviewGate, ReviewGateKey, ReviewGateStatus


def _gates_by_key(
    *,
    issues: list[str] | None = None,
    authoring_needs_review: bool = False,
    honesty_caveat: str = "",
    honesty_needs_review: bool = False,
    coverage_competencies: list[str] | None = None,
) -> dict[ReviewGateKey, ReviewGate]:
    gates = build_review_gates(
        FinalizeGateSignals(
            issues=issues or [],
            authoring_needs_review=authoring_needs_review,
            honesty_caveat=honesty_caveat,
            honesty_needs_review=honesty_needs_review,
            coverage_competencies=coverage_competencies or [],
        )
    )
    return {gate.key: gate for gate in gates}


def test_a_clean_build_records_all_four_gates_passed() -> None:
    gates = build_review_gates(
        FinalizeGateSignals(
            issues=[],
            authoring_needs_review=False,
            honesty_caveat="",
            honesty_needs_review=False,
            coverage_competencies=[],
        )
    )

    # Always four gates, in a stable order — the drawer shows the full picture, passed included.
    assert [gate.key for gate in gates] == [
        ReviewGateKey.STRUCTURE,
        ReviewGateKey.COVERAGE,
        ReviewGateKey.GROUNDING,
        ReviewGateKey.AUTHORING,
    ]
    assert all(gate.status is ReviewGateStatus.PASSED for gate in gates)
    assert all(gate.detail for gate in gates)  # even a passed gate says why in one line


def test_a_single_structure_issue_reads_singular() -> None:
    structure = _gates_by_key(issues=["No assessment items"])[ReviewGateKey.STRUCTURE]

    assert structure.status is ReviewGateStatus.WARNING
    assert "1 structural issue:" in structure.detail  # singular, not "issues"


def test_structure_issues_become_a_warning_naming_them() -> None:
    structure = _gates_by_key(issues=["No assessment items", "Lesson 2 lacks a worked example"])[
        ReviewGateKey.STRUCTURE
    ]

    assert structure.status is ReviewGateStatus.WARNING
    assert "2 structural issues" in structure.detail
    assert "No assessment items" in structure.detail


def test_a_long_issue_list_is_capped_with_a_count() -> None:
    structure = _gates_by_key(issues=[f"issue {n}" for n in range(6)])[ReviewGateKey.STRUCTURE]

    assert structure.status is ReviewGateStatus.WARNING
    assert "6 structural issues" in structure.detail
    assert "and 3 more" in structure.detail  # first 3 listed, remainder rolled up


def test_a_single_uncovered_competency_reads_singular() -> None:
    coverage = _gates_by_key(coverage_competencies=["Choosing a conjugate prior"])[
        ReviewGateKey.COVERAGE
    ]

    assert coverage.status is ReviewGateStatus.WARNING
    assert "1 promised competency" in coverage.detail  # singular noun
    assert "Choosing a conjugate prior" in coverage.detail


def test_a_long_uncovered_competency_list_is_capped_and_pluralised() -> None:
    coverage = _gates_by_key(coverage_competencies=[f"competency {n}" for n in range(6)])[
        ReviewGateKey.COVERAGE
    ]

    assert coverage.status is ReviewGateStatus.WARNING
    assert "6 promised competencies" in coverage.detail  # plural noun
    assert "and 2 more" in coverage.detail  # first 4 listed (its own cap), remainder rolled up


def test_a_grounding_caveat_carries_its_verbatim_text() -> None:
    caveat_text = "This course was not grounded in the real CLB 10 standard."
    grounding = _gates_by_key(honesty_caveat=caveat_text)[ReviewGateKey.GROUNDING]

    assert grounding.status is ReviewGateStatus.CAVEAT
    assert grounding.detail == caveat_text


def test_grounding_withheld_without_caveat_text_still_reads_as_a_caveat() -> None:
    grounding = _gates_by_key(honesty_needs_review=True, honesty_caveat="")[ReviewGateKey.GROUNDING]

    assert grounding.status is ReviewGateStatus.CAVEAT
    assert grounding.detail  # a non-empty fallback explanation


def test_author_low_confidence_becomes_a_warning() -> None:
    authoring = _gates_by_key(authoring_needs_review=True)[ReviewGateKey.AUTHORING]

    assert authoring.status is ReviewGateStatus.WARNING
    assert authoring.detail
