from lunaris_eval import CheckResult, EvalReport, evaluate_course
from lunaris_runtime.schema import (
    Claim,
    Course,
    Edge,
    KnowledgeComponent,
    Lesson,
    MerrillSegments,
    Module,
    Objective,
    PrerequisiteGraph,
    Segment,
    VerifierStatus,
)
from lunaris_runtime.schema.enums import BloomLevel


def _kc(kc_id: str, difficulty: float) -> KnowledgeComponent:
    return KnowledgeComponent(
        id=kc_id,
        label=kc_id,
        definition=kc_id,
        difficulty=difficulty,
        bloom_ceiling=BloomLevel.APPLY,
    )


def _lesson(lesson_id: str, claim: Claim) -> Lesson:
    blank = Segment(prose="x")
    return Lesson(
        id=lesson_id,
        segments=MerrillSegments(
            activate=blank,
            demonstrate=Segment(prose="x", claims=[claim]),
            apply=blank,
            integrate=blank,
        ),
    )


def _module(module_id: str, kc_id: str, difficulty: float, claim: Claim) -> Module:
    return Module(
        id=module_id,
        title=kc_id,
        kcs=[kc_id],
        objectives=[
            Objective(
                statement=f"apply {kc_id}",
                bloom_level=BloomLevel.APPLY,
                kc=kc_id,
                assessed_by=["i"],
            )
        ],
        lessons=[_lesson(f"{module_id}-l0", claim)],
        difficulty_index=difficulty,
    )


def _clean_course() -> Course:
    """The canonical passing baseline: a novice course a→b→c with c the goal, each module
    teaching one concept in order, every claim SUPPORTED. Every test mutates a copy of this."""
    graph = PrerequisiteGraph(
        nodes=[_kc("a", 0.1), _kc("b", 0.4), _kc("c", 0.8)],
        edges=[Edge(from_="a", to="b", strength=0.9), Edge(from_="b", to="c", strength=0.9)],
        is_acyclic=True,
        topo_order=["a", "b", "c"],
    )
    claim = Claim(text="grounded", supported_by="src::1", verifier_status=VerifierStatus.SUPPORTED)
    modules = [
        _module("m0", "a", 0.1, claim),
        _module("m1", "b", 0.4, claim),
        _module("m2", "c", 0.8, claim),
    ]
    return Course(id="c", topic="binary search", goal_concept="c", graph=graph, modules=modules)


def test_clean_course_passes_every_check_and_meets_dod() -> None:
    report = evaluate_course(_clean_course())

    assert report.passed
    assert report.meets_dod
    assert {check.name for check in report.checks} == {"prereq_order", "fit", "factuality"}


def test_incomplete_topo_order_fails_prereq_order() -> None:
    # Arrange — the topo order omits "c"; an independent verifier must reject it (it does NOT
    # trust the is_acyclic flag, which is still True here).
    course = _clean_course()
    course.graph.topo_order = ["a", "b"]

    # Act
    report = evaluate_course(course)

    # Assert
    assert not _check(report, "prereq_order").passed
    assert not report.passed
    assert not report.meets_dod


def test_edge_against_topo_order_fails_prereq_order() -> None:
    # Arrange — an edge c→a contradicts the a,b,c topological order
    course = _clean_course()
    course.graph.edges.append(Edge(from_="c", to="a", strength=0.5))

    # Act
    report = evaluate_course(course)

    # Assert
    assert not _check(report, "prereq_order").passed
    assert not report.passed


def test_module_out_of_sequence_fails_prereq_order() -> None:
    # Arrange — teach c, then b, then a: out of prerequisite order
    course = _clean_course()
    course.modules.reverse()

    # Act / Assert
    assert not _check(evaluate_course(course), "prereq_order").passed


def test_unknown_module_kc_fails_prereq_order() -> None:
    # Arrange
    course = _clean_course()
    course.modules[0].kcs = ["ghost"]

    # Act / Assert
    assert not _check(evaluate_course(course), "prereq_order").passed


def test_empty_course_fails_prereq_and_fit() -> None:
    # Arrange — no concepts, no modules
    course = Course(id="c", topic="t")

    # Act
    report = evaluate_course(course)

    # Assert
    assert not _check(report, "prereq_order").passed
    assert not _check(report, "fit").passed
    assert not report.meets_dod


def test_goal_not_last_fails_fit_only() -> None:
    # Arrange — declare an earlier concept the goal; prereq-order + factuality still hold
    course = _clean_course()
    course.goal_concept = "a"

    # Act
    report = evaluate_course(course)

    # Assert — fit fails, but the DoD (prereq-order + factuality) is unaffected
    assert not _check(report, "fit").passed
    assert _check(report, "prereq_order").passed
    assert _check(report, "factuality").passed
    assert report.meets_dod
    assert not report.passed


def test_live_unsupported_claim_fails_factuality() -> None:
    # Arrange — a claim left live (no citation) and not CUT
    course = _clean_course()
    course.modules[0].lessons[0].segments.demonstrate.claims = [
        Claim(text="ungrounded", supported_by=None, verifier_status=VerifierStatus.UNVERIFIED)
    ]

    # Act
    report = evaluate_course(course)

    # Assert
    assert not _check(report, "factuality").passed
    assert not report.passed
    assert not report.meets_dod


def test_cut_claim_passes_factuality() -> None:
    # Arrange — a CUT claim with no citation is the approved way to drop content from the gate
    course = _clean_course()
    course.modules[0].lessons[0].segments.demonstrate.claims = [
        Claim(text="dropped", supported_by=None, verifier_status=VerifierStatus.CUT)
    ]

    # Act / Assert — the gate still holds
    assert _check(evaluate_course(course), "factuality").passed


def test_unsupported_claim_in_any_phase_is_caught() -> None:
    # Arrange — put the offending claim in the apply phase (not demonstrate) to prove every
    # Merrill phase is scanned
    course = _clean_course()
    course.modules[0].lessons[0].segments.apply.claims = [
        Claim(text="ungrounded", supported_by=None, verifier_status=VerifierStatus.UNVERIFIED)
    ]

    # Act / Assert
    assert not _check(evaluate_course(course), "factuality").passed


def _check(report: EvalReport, name: str) -> CheckResult:
    match = next((check for check in report.checks if check.name == name), None)
    assert match is not None, f"no check named {name!r} in the report"
    return match
