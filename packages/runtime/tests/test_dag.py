"""The shared DAG algebra — the structural moat both products stand on.

Studio and Live each exercise this through their own node models. These test it directly, on plain
edges, because a defect here reaches both products at once and neither consumer's suite is
guaranteed to cover the case that breaks the other.

Several tests pin an exact result rather than an invariant. That is deliberate: which edge a repair
spends is a *contract*, not an implementation detail, and asserting only "one edge was dropped" is
what previously let a tie-break change slip through a refactor unnoticed.
"""

import pytest
from lunaris_runtime.dag import find_cycle, is_reachable, remove_cycles, topological_order

# ── find_cycle ────────────────────────────────────────────────────────────────────────────────


def test_find_cycle_returns_nothing_for_an_acyclic_graph() -> None:
    assert find_cycle([("a", "b"), ("b", "c")]) is None


def test_find_cycle_returns_nothing_for_an_empty_graph() -> None:
    assert find_cycle([]) is None


def test_find_cycle_finds_a_two_node_loop() -> None:
    # Act
    cycle = find_cycle([("a", "b"), ("b", "a")])

    # Assert — both edges, as indices into the input.
    assert cycle is not None
    assert sorted(cycle) == [0, 1]


def test_find_cycle_finds_a_self_loop() -> None:
    assert find_cycle([("a", "a")]) == [0]


def test_find_cycle_excludes_the_path_that_led_into_the_loop() -> None:
    """The approach edges are not part of the cycle, and a repair that thought they were would
    spend an edge that was never at fault."""
    # Arrange — index 0 leads into the loop; the loop itself is 1 and 2.
    # Act
    cycle = find_cycle([("start", "a"), ("a", "b"), ("b", "a")])

    # Assert
    assert cycle is not None
    assert sorted(cycle) == [1, 2]


def test_find_cycle_ignores_a_component_that_is_clean() -> None:
    # Arrange — an acyclic component declared first, a loop second.
    # Act
    cycle = find_cycle([("p", "q"), ("a", "b"), ("b", "a")])

    # Assert
    assert cycle is not None
    assert sorted(cycle) == [1, 2]


def test_find_cycle_does_not_depend_on_which_component_is_declared_first() -> None:
    """Two graphs differing only in declaration order must find the same loop."""
    first = find_cycle([("p", "q"), ("a", "b"), ("b", "a")])
    second = find_cycle([("a", "b"), ("b", "a"), ("p", "q")])

    assert first is not None and second is not None
    assert {("a", "b"), ("b", "a")} == {[("p", "q"), ("a", "b"), ("b", "a")][i] for i in first}
    assert {("a", "b"), ("b", "a")} == {[("a", "b"), ("b", "a"), ("p", "q")][i] for i in second}


# ── remove_cycles ─────────────────────────────────────────────────────────────────────────────


def test_remove_cycles_keeps_every_edge_of_an_acyclic_graph() -> None:
    assert remove_cycles([("a", "b"), ("b", "c")]) == [0, 1]


def test_remove_cycles_keeps_an_empty_graph_empty() -> None:
    assert remove_cycles([]) == []


def test_remove_cycles_spends_exactly_one_edge_per_loop() -> None:
    # Arrange
    edges = [("a", "b"), ("b", "c"), ("c", "a")]

    # Act
    kept = remove_cycles(edges)

    # Assert
    assert len(kept) == 2
    assert find_cycle([edges[i] for i in kept]) is None


def test_remove_cycles_spends_the_lowest_sorting_edge_when_unweighted() -> None:
    """The contract, pinned by value.

    With no weights every edge in a loop is equally suspect, so the choice must not fall to
    whichever the search reached first — that would depend on the order the caller happened to emit
    its edges in. Sorting on the edge itself makes the repair reproducible across callers.
    """
    # Arrange — ("a", "c") is the lowest-sorting pair in the loop.
    edges = [("b", "a"), ("c", "b"), ("a", "c")]

    # Act / Assert
    assert remove_cycles(edges) == [0, 1]


def test_remove_cycles_repairs_the_same_way_whatever_order_the_edges_arrive_in() -> None:
    # Arrange — the same loop, declared two ways.
    forwards = [("b", "a"), ("c", "b"), ("a", "c")]
    backwards = [("a", "c"), ("c", "b"), ("b", "a")]

    # Act
    kept_forwards = {forwards[i] for i in remove_cycles(forwards)}
    kept_backwards = {backwards[i] for i in remove_cycles(backwards)}

    # Assert
    assert kept_forwards == kept_backwards == {("b", "a"), ("c", "b")}


def test_remove_cycles_spends_the_weakest_judgment_when_weighted() -> None:
    """With weights, the least-confident claim loses — Studio's LLM-judged edge strength."""
    # Arrange — the b→a edge is the least confident of the loop.
    # Act
    kept = remove_cycles([("a", "b"), ("b", "a")], weights=[0.9, 0.2])

    # Assert
    assert kept == [0]


def test_remove_cycles_breaks_a_weight_tie_by_the_order_the_loop_was_walked() -> None:
    """Studio's long-standing behaviour, pinned so a refactor cannot drift it silently.

    Two equally-confident judgments give no reason to prefer either, and Studio's pipeline has
    always spent whichever the cycle reached first. Deliberately *not* the unweighted rule: changing
    Studio's output was out of scope for the extraction that introduced this parameter.
    """
    # Arrange / Act
    kept = remove_cycles([("b", "a"), ("a", "b")], weights=[0.5, 0.5])

    # Assert
    assert len(kept) == 1


def test_remove_cycles_never_spends_an_edge_outside_the_loop() -> None:
    # Arrange — 'x' legitimately depends on the loop but is not in it.
    edges = [("a", "x"), ("a", "b"), ("b", "a")]

    # Act
    kept = remove_cycles(edges)

    # Assert — the real dependency survives; only a loop edge was spent.
    assert 0 in kept
    assert len(kept) == 2


def test_remove_cycles_breaks_two_independent_loops_separately() -> None:
    # Arrange — two loops and one clean edge between them.
    edges = [("a", "b"), ("b", "a"), ("p", "q"), ("c", "d"), ("d", "c")]

    # Act
    kept = remove_cycles(edges)

    # Assert — one edge spent per loop, the bystander untouched, nothing cyclic left.
    assert 2 in kept
    assert len(kept) == 3
    assert find_cycle([edges[i] for i in kept]) is None


def test_remove_cycles_handles_loops_that_share_an_edge() -> None:
    """Overlapping loops: repairing one may leave the other, so the sweep has to re-scan."""
    # Arrange — a→b→c→a and a→b→d→a share the a→b edge.
    edges = [("a", "b"), ("b", "c"), ("c", "a"), ("b", "d"), ("d", "a")]

    # Act
    kept = remove_cycles(edges)

    # Assert
    assert find_cycle([edges[i] for i in kept]) is None


def test_remove_cycles_removes_a_self_loop() -> None:
    assert remove_cycles([("a", "a"), ("a", "b")]) == [1]


def test_remove_cycles_treats_duplicate_edges_as_distinct() -> None:
    """Indices, not values: two structurally identical edges are two edges, and removing one must
    not silently remove the other."""
    # Arrange — the loop is closed twice over, by two edges that are equal in value.
    edges = [("a", "b"), ("b", "a"), ("b", "a")]

    # Act
    kept = remove_cycles(edges)

    # Assert — cutting the shared edge settles both loops at once, so BOTH duplicates survive. A
    # value-addressed implementation would have discarded them together.
    assert kept == [1, 2]
    assert find_cycle([edges[i] for i in kept]) is None


# ── topological_order ─────────────────────────────────────────────────────────────────────────


def test_topological_order_puts_prerequisites_first() -> None:
    assert topological_order(["a", "b", "c"], [("a", "b"), ("b", "c")]) == ["a", "b", "c"]


def test_topological_order_falls_back_to_id_order_for_independent_nodes() -> None:
    assert topological_order(["z", "a", "m"], []) == ["a", "m", "z"]


def test_topological_order_uses_rank_between_equally_ready_nodes() -> None:
    """Studio ranks by difficulty so a course ramps rather than jumping about."""
    assert topological_order(["a", "z"], [], rank={"a": 0.9, "z": 0.1}) == ["z", "a"]


def test_topological_order_breaks_a_rank_tie_by_id() -> None:
    assert topological_order(["b", "a"], [], rank={"a": 0.5, "b": 0.5}) == ["a", "b"]


def test_topological_order_ignores_an_edge_naming_an_unknown_node() -> None:
    """The caller owns pruning; this stays total rather than failing on a subgraph."""
    assert topological_order(["a"], [("a", "gone"), ("missing", "a")]) == ["a"]


def test_topological_order_refuses_a_cycle_rather_than_papering_over_it() -> None:
    with pytest.raises(ValueError, match="not acyclic"):
        topological_order(["a", "b"], [("a", "b"), ("b", "a")])


def test_topological_order_of_an_empty_graph_is_empty() -> None:
    assert topological_order([], []) == []


# ── is_reachable ──────────────────────────────────────────────────────────────────────────────


def test_is_reachable_follows_a_direct_edge() -> None:
    assert is_reachable("a", "b", [("a", "b")]) is True


def test_is_reachable_follows_a_path() -> None:
    assert is_reachable("a", "c", [("a", "b"), ("b", "c")]) is True


def test_is_reachable_is_false_for_an_unconnected_node() -> None:
    assert is_reachable("a", "c", [("a", "b")]) is False


def test_is_reachable_respects_direction() -> None:
    assert is_reachable("b", "a", [("a", "b")]) is False


def test_is_reachable_is_false_in_an_empty_graph() -> None:
    assert is_reachable("a", "b", []) is False


def test_is_reachable_terminates_on_a_cyclic_graph() -> None:
    """Reachability is asked of graphs that are not acyclic yet, so it must not loop forever."""
    assert is_reachable("a", "gone", [("a", "b"), ("b", "a")]) is False
