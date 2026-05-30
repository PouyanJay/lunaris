from lunaris_graph.builder import PrerequisiteGraphBuilder
from lunaris_graph.judges import StubPrereqJudge

from .golden import BINARY_SEARCH


def _positions(topo: list[str]) -> dict[str, int]:
    return {kc_id: i for i, kc_id in enumerate(topo)}


async def test_builder_recovers_golden_dag_and_cleans_noise() -> None:
    # Arrange — feed the golden edges PLUS a redundant edge and a cycle-inducing edge
    noisy = [
        *BINARY_SEARCH.edges,
        ("comparison", "binary_search"),  # redundant (via sorted_order)
        ("binary_search", "arrays"),  # induces a cycle — must be removed
    ]
    builder = PrerequisiteGraphBuilder(StubPrereqJudge(noisy))

    # Act
    graph = await builder.build(BINARY_SEARCH.kcs, frontier=[], goal=BINARY_SEARCH.goal)

    # Assert — assembly recovered exactly the minimal golden DAG, acyclic, well-ordered
    assert graph.is_acyclic
    assert {(e.from_, e.to) for e in graph.edges} == set(BINARY_SEARCH.edges)

    pos = _positions(graph.topo_order)
    for prereq, dependent in BINARY_SEARCH.edges:
        assert pos[prereq] < pos[dependent], f"{prereq} must precede {dependent}"


async def test_builder_auto_levels_for_an_advanced_learner() -> None:
    # Arrange — learner already knows everything but the goal itself
    builder = PrerequisiteGraphBuilder(StubPrereqJudge(BINARY_SEARCH.edges))
    known = ["comparison", "arrays", "loops", "sorted_order"]

    # Act
    graph = await builder.build(BINARY_SEARCH.kcs, frontier=known, goal=BINARY_SEARCH.goal)

    # Assert — a deep frontier yields a short course (just the goal)
    assert [n.id for n in graph.nodes] == ["binary_search"]
    assert graph.edges == []


async def test_builder_full_ladder_for_a_novice() -> None:
    # Arrange — empty frontier (MVP default): full ladder to the goal
    builder = PrerequisiteGraphBuilder(StubPrereqJudge(BINARY_SEARCH.edges))

    # Act
    graph = await builder.build(BINARY_SEARCH.kcs, frontier=[], goal=BINARY_SEARCH.goal)

    # Assert — all five KCs present, goal last
    assert len(graph.nodes) == 5
    assert graph.topo_order[-1] == "binary_search"
