"""GraphAssembler — the deterministic correctness core: cycle removal (weakest-edge), transitive
reduction, frontier pruning, and the validated topological teaching order."""

import pytest
from lunaris_graph.assembler import GraphAssembler
from lunaris_runtime.schema import BloomLevel, Edge, KnowledgeComponent


def _kc(kc_id: str, difficulty: float) -> KnowledgeComponent:
    return KnowledgeComponent(
        id=kc_id,
        label=kc_id,
        definition=kc_id,
        difficulty=difficulty,
        bloom_ceiling=BloomLevel.APPLY,
    )


def _edge(a: str, b: str, strength: float = 0.9) -> Edge:
    return Edge(from_=a, to=b, strength=strength)


def test_candidate_pairs_are_easier_to_harder_only() -> None:
    # Arrange
    kcs = [_kc("hard", 0.8), _kc("easy", 0.2), _kc("mid", 0.5)]

    # Act
    pairs = GraphAssembler().candidate_pairs(kcs)

    # Assert — every pair goes from lower difficulty to higher, no reverse pairs
    assert [(a.id, b.id) for a, b in pairs] == [
        ("easy", "mid"),
        ("easy", "hard"),
        ("mid", "hard"),
    ]


def test_remove_cycles_breaks_the_weakest_edge() -> None:
    # Arrange — a 3-cycle a->b->c->a; the c->a edge is weakest
    edges = [_edge("a", "b", 0.9), _edge("b", "c", 0.8), _edge("c", "a", 0.3)]

    # Act
    kept = GraphAssembler().remove_cycles(edges)

    # Assert
    assert GraphAssembler().is_acyclic(kept)
    assert ("c", "a") not in [(e.from_, e.to) for e in kept]


def test_acyclic_inputs_are_returned_untouched() -> None:
    # Arrange — a diamond (a→b, a→c, b→d, c→d): converging paths but no cycle.
    edges = [_edge("a", "b"), _edge("a", "c"), _edge("b", "d"), _edge("c", "d")]

    # Act
    kept = GraphAssembler().remove_cycles(edges)

    # Assert — nothing was cut; convergence must never be mistaken for a cycle.
    assert kept == edges
    assert GraphAssembler().is_acyclic(edges)


def test_self_loop_is_detected_and_removed() -> None:
    # Arrange — a KC judged prerequisite to itself (the degenerate judgment error).
    edges = [_edge("a", "a", 0.5), _edge("a", "b", 0.9)]
    assembler = GraphAssembler()

    # Act / Assert
    assert not assembler.is_acyclic(edges)
    kept = assembler.remove_cycles(edges)
    assert [(e.from_, e.to) for e in kept] == [("a", "b")]


def test_two_node_cycle_keeps_the_stronger_direction() -> None:
    # Arrange — mutual prerequisites a⇄b; the model was more confident in a→b.
    edges = [_edge("a", "b", 0.9), _edge("b", "a", 0.4)]

    # Act
    kept = GraphAssembler().remove_cycles(edges)

    # Assert — the weaker judgment loses, the stronger survives.
    assert [(e.from_, e.to) for e in kept] == [("a", "b")]


def test_multiple_independent_cycles_are_all_broken() -> None:
    # Arrange — two disjoint 2-cycles plus an acyclic bystander edge.
    edges = [
        _edge("a", "b", 0.9),
        _edge("b", "a", 0.2),
        _edge("c", "d", 0.8),
        _edge("d", "c", 0.1),
        _edge("x", "y", 0.7),
    ]
    assembler = GraphAssembler()

    # Act
    kept = assembler.remove_cycles(edges)

    # Assert — both cycles broken at their weakest edge; the bystander untouched.
    assert assembler.is_acyclic(kept)
    pairs = {(e.from_, e.to) for e in kept}
    assert pairs == {("a", "b"), ("c", "d"), ("x", "y")}


def test_overlapping_cycles_are_broken_iteratively() -> None:
    # Arrange — two cycles sharing the edge b→c: a→b→c→a and b→c→d→b. Breaking one may or may
    # not break the other, so removal must iterate until the whole graph is a DAG.
    edges = [
        _edge("a", "b", 0.9),
        _edge("b", "c", 0.8),
        _edge("c", "a", 0.3),
        _edge("c", "d", 0.7),
        _edge("d", "b", 0.2),
    ]
    assembler = GraphAssembler()

    # Act
    kept = assembler.remove_cycles(edges)

    # Assert — fully acyclic, and only the weak judgment errors were sacrificed.
    assert assembler.is_acyclic(kept)
    pairs = {(e.from_, e.to) for e in kept}
    assert ("c", "a") not in pairs
    assert ("d", "b") not in pairs
    assert {("a", "b"), ("b", "c"), ("c", "d")} <= pairs


def test_cycle_in_one_component_is_found_among_disconnected_components() -> None:
    # Arrange — an acyclic component alphabetically FIRST, the cycle hidden in a later one (the
    # detector must keep scanning components after a clean one).
    edges = [_edge("a", "b"), _edge("m", "n", 0.9), _edge("n", "m", 0.5)]
    assembler = GraphAssembler()

    # Act / Assert
    assert not assembler.is_acyclic(edges)
    kept = assembler.remove_cycles(edges)
    assert {(e.from_, e.to) for e in kept} == {("a", "b"), ("m", "n")}


def test_topological_sort_refuses_a_cyclic_graph() -> None:
    # Arrange — the sort is the last line of defence; cyclic input must raise, never emit a
    # partial teaching order.
    nodes = [_kc("a", 0.1), _kc("b", 0.2)]
    edges = [_edge("a", "b"), _edge("b", "a")]

    # Act / Assert
    with pytest.raises(ValueError, match="not acyclic"):
        GraphAssembler().topological_sort(nodes, edges)


def test_transitive_reduction_drops_redundant_edge() -> None:
    # Arrange — a->b->c plus a redundant a->c
    edges = [_edge("a", "b"), _edge("b", "c"), _edge("a", "c")]

    # Act
    kept = {(e.from_, e.to) for e in GraphAssembler().transitive_reduction(edges)}

    # Assert
    assert kept == {("a", "b"), ("b", "c")}


def test_topological_sort_respects_every_edge_and_tiebreaks_by_difficulty() -> None:
    # Arrange
    nodes = [_kc("a", 0.1), _kc("b", 0.2), _kc("c", 0.3)]
    edges = [_edge("a", "c"), _edge("b", "c")]
    assembler = GraphAssembler()

    # Act
    order = assembler.topological_sort(nodes, edges)

    # Assert — c last; a before b by difficulty tiebreak
    position = {kc_id: i for i, kc_id in enumerate(order)}
    assert position["a"] < position["c"]
    assert position["b"] < position["c"]
    assert position["a"] < position["b"]


def test_prune_to_frontier_keeps_only_what_is_needed() -> None:
    # Arrange — a->b->goal; learner already knows `a`
    nodes = {"a", "b", "goal"}
    edges = [_edge("a", "b"), _edge("b", "goal")]

    # Act
    kept_ids, kept_edges = GraphAssembler().prune_to_frontier(
        nodes, edges, frontier=["a"], goal="goal"
    )

    # Assert — `a` is dropped (known); b and goal remain
    assert kept_ids == {"b", "goal"}
    assert {(e.from_, e.to) for e in kept_edges} == {("b", "goal")}
