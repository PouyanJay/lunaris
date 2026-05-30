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
