from lunaris_agent import MinimalCritic
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


def _segment(claim: Claim | None = None) -> Segment:
    return Segment(prose="x", claims=[claim] if claim else [])


def _lesson(lesson_id: str, claim: Claim | None = None) -> Lesson:
    return Lesson(
        id=lesson_id,
        segments=MerrillSegments(
            activate=_segment(),
            demonstrate=_segment(claim),
            apply=_segment(),
            integrate=_segment(),
        ),
    )


def _clean_course() -> Course:
    nodes = [
        KnowledgeComponent(
            id="a", label="A", definition="a", difficulty=0.2, bloom_ceiling=BloomLevel.APPLY
        ),
        KnowledgeComponent(
            id="b", label="B", definition="b", difficulty=0.6, bloom_ceiling=BloomLevel.APPLY
        ),
    ]
    graph = PrerequisiteGraph(
        nodes=nodes,
        edges=[Edge(from_="a", to="b", strength=0.9)],
        is_acyclic=True,
        topo_order=["a", "b"],
    )
    supported = Claim(
        text="grounded", supported_by="src::1", verifier_status=VerifierStatus.SUPPORTED
    )
    modules = [
        Module(
            id="m0",
            title="A",
            kcs=["a"],
            objectives=[
                Objective(
                    statement="apply a", bloom_level=BloomLevel.APPLY, kc="a", assessed_by=["i0"]
                )
            ],
            lessons=[_lesson("m0-l0", supported)],
            difficulty_index=0.2,
        ),
        Module(
            id="m1",
            title="B",
            kcs=["b"],
            objectives=[
                Objective(
                    statement="apply b", bloom_level=BloomLevel.APPLY, kc="b", assessed_by=["i1"]
                )
            ],
            lessons=[_lesson("m1-l0")],
            difficulty_index=0.6,
        ),
    ]
    return Course(id="c", topic="t", goal_concept="b", graph=graph, modules=modules)


def test_clean_course_passes_with_no_issues() -> None:
    assert MinimalCritic().review(_clean_course()) == []


def test_unknown_module_kc_is_flagged() -> None:
    # Arrange
    course = _clean_course()
    course.modules[0].kcs = ["ghost"]

    # Act
    issues = MinimalCritic().review(course)

    # Assert
    assert any("ghost" in issue for issue in issues)


def test_decreasing_module_difficulty_is_flagged() -> None:
    course = _clean_course()
    course.modules[1].difficulty_index = 0.1  # below module 0's 0.2

    issues = MinimalCritic().review(course)

    assert any("difficulty decreases" in issue for issue in issues)


def test_live_unsupported_claim_trips_the_publish_gate() -> None:
    # Arrange — a claim left live (supported_by None) but not CUT
    course = _clean_course()
    bad = Claim(text="ungrounded", supported_by=None, verifier_status=VerifierStatus.SUPPORTED)
    course.modules[0].lessons = [_lesson("m0-l0", bad)]

    # Act
    issues = MinimalCritic().review(course)

    # Assert
    assert any("publish gate" in issue for issue in issues)


def test_objective_without_assessment_is_flagged() -> None:
    course = _clean_course()
    course.modules[0].objectives[0].assessed_by = []

    issues = MinimalCritic().review(course)

    assert any("assessment item" in issue for issue in issues)
