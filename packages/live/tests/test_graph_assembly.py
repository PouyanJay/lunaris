"""The assembly invariants — Live's correctness moat.

A compiler may propose any structure; only this module may declare it sound. These tests pin the
guarantees the rest of the product leans on, written against ``assemble``'s signature rather than
its internals — which is what let T2 move the body onto the shared ``lunaris_runtime.dag`` algebra
without touching a single assertion here.

The algebra itself is tested directly in ``packages/runtime/tests/test_dag.py``. What these cover is
Live's own translation on top of it: a concept carrying its prerequisites, dangling and duplicate
claims pruned, and the repair reported rather than absorbed.
"""

from lunaris_live.graph import ConceptGraph, ConceptNode, assemble


def _graph(*nodes: ConceptNode) -> ConceptGraph:
    return ConceptGraph(graph_id="g1", topic="t", nodes=list(nodes))


def _node(node_id: str, *requires: str) -> ConceptNode:
    return ConceptNode(id=node_id, name=node_id, definition="d", requires=list(requires))


def test_prerequisites_come_before_the_concepts_that_need_them() -> None:
    # Arrange — declared out of order, so a compiler's ordering cannot be what makes this pass.
    graph = _graph(_node("c", "b"), _node("a"), _node("b", "a"))

    # Act
    assembled = assemble(graph)

    # Assert
    assert assembled.is_acyclic is True
    assert assembled.topo_order == ["a", "b", "c"]


def test_a_prerequisite_naming_an_unknown_concept_is_dropped() -> None:
    """The most common decomposition error: a confident reference to a concept that isn't there.

    It must not strand the node — a concept waiting forever on a prerequisite that will never
    arrive is a concept the session can never teach.
    """
    # Arrange
    graph = _graph(_node("a"), _node("b", "a", "ghost"))

    # Act
    assembled = assemble(graph)

    # Assert
    assert {node.id: node.requires for node in assembled.nodes} == {"a": [], "b": ["a"]}
    assert assembled.topo_order == ["a", "b"]


def test_a_dependency_loop_is_broken_rather_than_shipped() -> None:
    # Arrange — a ↔ b, which no ordering can satisfy.
    graph = _graph(_node("a", "b"), _node("b", "a"), _node("c"))

    # Act
    assembled = assemble(graph)

    # Assert — every concept is reachable and the graph is honestly marked acyclic afterwards.
    assert assembled.is_acyclic is True
    assert sorted(assembled.topo_order) == ["a", "b", "c"]


def test_breaking_a_loop_keeps_the_dependencies_that_were_never_in_it() -> None:
    """Repairing a cycle must cost one edge, not every edge the cycle touched.

    A decomposition that loops a → b → c → a is wrong about *one* of those three claims. If the
    repair flattens all of them, three concepts that genuinely build on each other are handed to the
    session as unrelated starting points — a worse curriculum than the one with the loop in it, and
    silently so.
    """
    # Arrange — a three-concept loop, plus a legitimate prerequisite from outside it.
    graph = _graph(_node("root"), _node("a", "c"), _node("b", "a", "root"), _node("c", "b"))

    # Act
    assembled = assemble(graph)
    requires = {node.id: node.requires for node in assembled.nodes}

    # Assert — the graph is teachable again ...
    assert assembled.is_acyclic is True
    assert sorted(assembled.topo_order) == ["a", "b", "c", "root"]

    # ... and only one of the loop's three edges was spent to get there.
    loop_edges_kept = sum(
        1
        for dependent, prerequisite in (("a", "c"), ("b", "a"), ("c", "b"))
        if prerequisite in requires[dependent]
    )
    assert loop_edges_kept == 2, f"expected one edge dropped, kept {loop_edges_kept} of 3"

    # The edge from outside the loop was never in question and must survive untouched.
    assert "root" in requires["b"]


def test_repairing_a_loop_spares_concepts_that_merely_depend_on_it() -> None:
    """Only edges *inside* the loop may be cut — not edges belonging to its downstream dependents.

    A concept that legitimately builds on a looped one is not itself part of the loop, and cutting
    its prerequisite repairs nothing while losing something real. Node ids come from concept slugs,
    so whether a dependent happens to sort before the loop's own members is pure chance — which is
    exactly why this must not be what decides which edge gets spent.
    """
    # Arrange — 'a' sorts first but is downstream of the loop; the actual cycle is x ↔ y.
    graph = _graph(_node("a", "x"), _node("x", "y"), _node("y", "x"))

    # Act
    assembled = assemble(graph)
    requires = {node.id: node.requires for node in assembled.nodes}

    # Assert — the loop is gone ...
    assert assembled.is_acyclic is True
    # ... exactly one of the two loop edges was spent ...
    assert sum(1 for dep, pre in (("x", "y"), ("y", "x")) if pre in requires[dep]) == 1
    # ... and the dependent's real prerequisite is untouched.
    assert requires["a"] == ["x"]


def test_which_edge_a_repair_spends_is_fixed_and_not_left_to_input_order() -> None:
    """The tie-break itself, pinned by value.

    Every edge in an unweighted loop is equally suspect, so the rule is the lowest-sorting
    ``(prerequisite, dependent)`` pair — deliberately not "whichever the search reached first",
    which would make the repair depend on the order the compiler happened to emit concepts in. Two
    compiles of one topic have to be comparable, and a T2 refactor already changed this rule once
    without any test noticing.
    """
    # Arrange — the same loop, declared in two different orders.
    forwards = _graph(_node("a", "b"), _node("b", "c"), _node("c", "a"))
    backwards = _graph(_node("c", "a"), _node("b", "c"), _node("a", "b"))

    # Act
    first = {node.id: node.requires for node in assemble(forwards).nodes}
    second = {node.id: node.requires for node in assemble(backwards).nodes}

    # Assert — the lowest-sorting edge (c's claim on a) is the one spent, either way round.
    assert first == second == {"a": ["b"], "b": ["c"], "c": []}


def test_a_concept_cannot_require_itself() -> None:
    # Arrange
    graph = _graph(_node("a", "a"))

    # Act
    assembled = assemble(graph)

    # Assert
    assert assembled.nodes[0].requires == []
    assert assembled.topo_order == ["a"]


def test_a_prerequisite_claimed_twice_counts_once() -> None:
    """ "Needs X, and also X" says nothing twice — and left in, one dependency would look like two
    edges to everything downstream, including the cycle repair."""
    # Arrange
    graph = _graph(_node("a"), _node("b", "a", "a"))

    # Act
    assembled = assemble(graph)

    # Assert
    assert {node.id: node.requires for node in assembled.nodes} == {"a": [], "b": ["a"]}
    assert assembled.topo_order == ["a", "b"]


def test_assembly_is_reproducible() -> None:
    """Two compiles of the same concepts assemble identically, so a version diff is readable."""
    # Arrange — independent concepts, where any tie-break would otherwise be arbitrary.
    graph = _graph(_node("z"), _node("m"), _node("a"))

    # Act
    first, second = assemble(graph), assemble(graph)

    # Assert
    assert first.topo_order == second.topo_order == ["a", "m", "z"]


def test_an_empty_graph_assembles_rather_than_failing() -> None:
    """A decomposition can legitimately come back empty; that is a 0-node graph, not a crash."""
    # Act
    assembled = assemble(_graph())

    # Assert
    assert assembled.topo_order == []
    assert assembled.is_acyclic is True
