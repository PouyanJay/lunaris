"""project_video_dependencies: the course's PrerequisiteGraph projected to a lesson-video dependency
DAG. For each lesson video, the upstream lesson videos it builds on (its prerequisites), in
topological teaching order — derived from the real prereq edges + Module.kcs, not positional order.
It feeds the planner the upstream context so a (re)plan stays consistent with the course."""

from lunaris_runtime.schema import (
    BloomLevel,
    Course,
    Edge,
    KnowledgeComponent,
    Lesson,
    MerrillSegments,
    Module,
    PrerequisiteGraph,
    Segment,
)
from lunaris_video.planning import project_video_dependencies


def _kc(kc_id: str) -> KnowledgeComponent:
    return KnowledgeComponent(
        id=kc_id,
        label=kc_id,
        definition=f"the {kc_id} concept",
        difficulty=0.5,
        bloom_ceiling=BloomLevel.UNDERSTAND,
    )


def _lesson(lesson_id: str) -> Lesson:
    blank = Segment(prose="")
    return Lesson(
        id=lesson_id,
        segments=MerrillSegments(
            activate=blank,
            demonstrate=Segment(prose="the core teaching"),
            apply=blank,
            integrate=blank,
        ),
    )


def _module(module_id: str, *, kcs: list[str], lesson_ids: list[str]) -> Module:
    return Module(
        id=module_id, title=module_id, kcs=kcs, lessons=[_lesson(lid) for lid in lesson_ids]
    )


def _chain_course() -> Course:
    """M1 teaches k1 (lesson m1-l0); M2 teaches k2 (lesson m2-l0); k1 is a prerequisite of k2."""
    graph = PrerequisiteGraph(
        nodes=[_kc("k1"), _kc("k2")],
        edges=[Edge(from_="k1", to="k2", strength=1.0)],  # k1 must be learned before k2
        topo_order=["k1", "k2"],
        is_acyclic=True,
    )
    return Course(
        id="c",
        topic="t",
        modules=[
            _module("m1", kcs=["k1"], lesson_ids=["m1-l0"]),
            _module("m2", kcs=["k2"], lesson_ids=["m2-l0"]),
        ],
        graph=graph,
    )


def test_downstream_lesson_depends_on_its_prerequisite_lesson() -> None:
    # Arrange / Act
    dep = project_video_dependencies(_chain_course())

    # Assert — m2's KC (k2) requires m1's KC (k1), so m2's video depends on m1's; m1 is a root.
    assert dep.upstream_of("m2-l0") == ("m1-l0",)
    assert dep.upstream_of("m1-l0") == ()


def test_order_follows_the_topological_teaching_order() -> None:
    # Arrange / Act
    dep = project_video_dependencies(_chain_course())

    # Assert — upstream before downstream (the generation order).
    assert dep.order == ("m1-l0", "m2-l0")


def test_transitive_prerequisites_are_included() -> None:
    # Arrange — k1 -> k2 -> k3 across three modules; m3 transitively depends on m1.
    graph = PrerequisiteGraph(
        nodes=[_kc("k1"), _kc("k2"), _kc("k3")],
        edges=[Edge(from_="k1", to="k2", strength=1.0), Edge(from_="k2", to="k3", strength=1.0)],
        topo_order=["k1", "k2", "k3"],
        is_acyclic=True,
    )
    course = Course(
        id="c",
        topic="t",
        modules=[
            _module("m1", kcs=["k1"], lesson_ids=["m1-l0"]),
            _module("m2", kcs=["k2"], lesson_ids=["m2-l0"]),
            _module("m3", kcs=["k3"], lesson_ids=["m3-l0"]),
        ],
        graph=graph,
    )

    # Act
    dep = project_video_dependencies(course)

    # Assert — m3 depends on BOTH m2 (direct) and m1 (transitive), in topo order.
    assert dep.upstream_of("m3-l0") == ("m1-l0", "m2-l0")


def test_same_module_lessons_are_never_each_others_upstream() -> None:
    # Arrange — k1 -> k2, but BOTH KCs live in one module taught by two lessons. The prereq edge
    # must NOT make one lesson depend on the other: same-module lessons share KCs (the real
    # dependency is cross-module).
    graph = PrerequisiteGraph(
        nodes=[_kc("k1"), _kc("k2")],
        edges=[Edge(from_="k1", to="k2", strength=1.0)],
        topo_order=["k1", "k2"],
        is_acyclic=True,
    )
    course = Course(
        id="c",
        topic="t",
        modules=[_module("m1", kcs=["k1", "k2"], lesson_ids=["m1-l0", "m1-l1"])],
        graph=graph,
    )

    # Act
    dep = project_video_dependencies(course)

    # Assert
    assert dep.upstream_of("m1-l0") == ()
    assert dep.upstream_of("m1-l1") == ()


def test_an_ungraphed_course_yields_no_dependencies() -> None:
    # Arrange — modules with KCs but a default (empty) graph: no edges, no topo_order.
    course = Course(
        id="c",
        topic="t",
        modules=[
            _module("m1", kcs=["k1"], lesson_ids=["m1-l0"]),
            _module("m2", kcs=["k2"], lesson_ids=["m2-l0"]),
        ],
    )

    # Act
    dep = project_video_dependencies(course)

    # Assert — every lesson a root; order falls back to appearance.
    assert dep.upstream_of("m2-l0") == ()
    assert dep.upstream_of("m1-l0") == ()
    assert dep.order == ("m1-l0", "m2-l0")
