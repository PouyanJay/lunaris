"""The gate's own gate (Phase 1, T9).

``complaints_about`` is what decides whether ten real compiles passed, and it runs behind a real
key where a mistake costs money and a re-run. A checker that silently accepted everything would
report ten green topics and prove nothing — so each check here is shown to fire by taking a map
that passes and breaking it that one way.

The digest gets the same treatment for the same reason: it is the artifact the human reviewer
actually reads, and one that quietly omitted the misconceptions would hide the field the whole
teaching spec exists for.
"""

import pytest
from graph_quality import complaints_about, digest
from lunaris_live.graph import (
    ConceptGraph,
    ConceptNode,
    MasteryCriterion,
    MasteryCriterionKind,
    NodeProvenance,
    TeachingSpec,
    assemble,
)


def _node(node_id: str, name: str, *, requires: list[str] | None = None) -> ConceptNode:
    return ConceptNode(
        id=node_id,
        name=name,
        definition=f"What {name.lower()} actually means, said in a sentence.",
        requires=requires or [],
        aliases=[f"{name} (informal)"],
        teaching_spec=TeachingSpec(
            objective=f"Predict what {name.lower()} does.",
            misconceptions=[f"{name} is the same as the thing before it."],
        ),
        mastery_criteria=[
            MasteryCriterion(
                kind=MasteryCriterionKind.PREDICT,
                statement=f"Predict what happens to {name.lower()} when the input doubles.",
            )
        ],
    )


def _good_graph(count: int = 10) -> ConceptGraph:
    """A map with nothing wrong with it — a chain, so every prerequisite is real and ordered."""
    nodes = [
        _node(f"c{i}", f"Concept {i}", requires=[f"c{i - 1}"] if i else []) for i in range(count)
    ]
    return assemble(ConceptGraph(graph_id="g1", topic="A subject", nodes=nodes))


def test_a_sound_map_draws_no_complaints() -> None:
    """The baseline every other case in this file mutates. Without it, a checker that complained
    about everything would look just as green as one that worked."""
    assert complaints_about(_good_graph()) == []


def _broken(**update: object) -> ConceptGraph:
    """The good map with one thing changed — ``model_copy`` so assembly's derived fields survive
    exactly as compiled, which is what lets a test break the *claim* rather than the wiring."""
    return _good_graph().model_copy(update=update)


@pytest.mark.parametrize(
    ("graph", "expected"),
    [
        pytest.param(_broken(is_acyclic=False), "not acyclic", id="a cycle"),
        pytest.param(_broken(topo_order=["c0", "c1"]), "does not cover", id="a truncated order"),
        pytest.param(
            _broken(topo_order=[*_good_graph().topo_order[::-1]]),
            "taught before its prerequisite",
            id="reversed teaching order",
        ),
        pytest.param(
            _good_graph().model_copy(
                update={
                    "nodes": [*_good_graph().nodes[:-1], _node("c9", "Nine", requires=["gone"])]
                }
            ),
            "which is not on the map",
            id="a dangling prerequisite",
        ),
        pytest.param(_broken(nodes=_good_graph().nodes[:3]), "outside the", id="too few concepts"),
        pytest.param(
            _good_graph(count=40), "outside the", id="more concepts than three minutes buys"
        ),
        pytest.param(
            _broken(topo_order=[*_good_graph().topo_order, "c0"]),
            "repeats a concept",
            id="a concept taught twice",
        ),
    ],
)
def test_a_structurally_broken_map_is_refused(graph: ConceptGraph, expected: str) -> None:
    assert any(expected in complaint for complaint in complaints_about(graph)), (
        f"the checker accepted a map it should refuse; it said: {complaints_about(graph)}"
    )


@pytest.mark.parametrize(
    ("update", "expected"),
    [
        # A missing spec is deliberately absent from this table: one of them is tolerated by
        # design, so it is a *share* claim, pinned by its own test below.
        pytest.param(
            {"teaching_spec": TeachingSpec(objective="Do it.", misconceptions=[])},
            "no misconceptions",
            id="a spec with nothing to hunt for",
        ),
        pytest.param({"mastery_criteria": []}, "no mastery criteria", id="nothing checkable"),
        pytest.param(
            {
                "mastery_criteria": [
                    MasteryCriterion(
                        kind=MasteryCriterionKind.EXPLAIN,
                        statement="Understands that gradients point uphill.",
                    )
                ]
            },
            "knowing, not doing",
            id="mastery as knowledge",
        ),
        pytest.param(
            {"provenance": NodeProvenance.EXTENDED}, "cold compile", id="wrong provenance"
        ),
        pytest.param(
            {"definition": "Concept 0"}, "restates its name", id="a definition that isn't"
        ),
    ],
)
def test_an_unteachable_concept_is_refused(update: dict[str, object], expected: str) -> None:
    """Every one of these is a thing the *schema* allows on purpose — a node survives a failed
    authoring call rather than taking the map down with it. Which is exactly why the gate has to
    catch them: nothing below this line will."""
    # Arrange — one concept of an otherwise sound map, broken one way.
    good = _good_graph()
    nodes = [good.nodes[0].model_copy(update=update), *good.nodes[1:]]

    # Act
    complaints = complaints_about(good.model_copy(update={"nodes": nodes}))

    # Assert
    assert any(expected in complaint for complaint in complaints), (
        f"the checker accepted an unteachable concept; it said: {complaints}"
    )


def test_a_map_nobody_can_ask_about_in_their_own_words_is_refused() -> None:
    """C2 matches a learner's wording against names and aliases. Every alias gone means every
    question has to be asked in the compiler's vocabulary, which is the failure C2 exists to
    prevent — and it is invisible in a map that is otherwise perfect."""
    # Arrange
    good = _good_graph()
    nodes = [node.model_copy(update={"aliases": []}) for node in good.nodes]

    # Act / Assert
    complaints = complaints_about(good.model_copy(update={"nodes": nodes}))
    assert any("alias" in complaint for complaint in complaints)


def test_the_unspecified_share_is_a_share_not_a_count() -> None:
    """One failed authoring call in a map of ten is a bad minute at the provider; a quarter of them
    is the prompt. A gate that fired on the first would cost a re-run of all ten topics."""
    good = _good_graph(count=10)
    one_missing = [good.nodes[0].model_copy(update={"teaching_spec": None}), *good.nodes[1:]]
    assert not [
        c
        for c in complaints_about(good.model_copy(update={"nodes": one_missing}))
        if "teaching spec" in c
    ]

    three_missing = [
        *(node.model_copy(update={"teaching_spec": None}) for node in good.nodes[:3]),
        *good.nodes[3:],
    ]
    assert [
        c
        for c in complaints_about(good.model_copy(update={"nodes": three_missing}))
        if "teaching spec" in c
    ]


def test_the_digest_carries_what_the_reviewer_has_to_judge() -> None:
    """The reviewer answers "right concepts, right order, nothing invented" from this text alone.
    Anything the digest drops is a question they cannot be asked."""
    # Arrange
    graph = _good_graph(count=3)

    # Act
    written = digest(graph, elapsed_s=42.5)

    # Assert — the order is the graph's own, and it is numbered so "is this the right order" is a
    # question the reader can answer without reconstructing it.
    assert written.index("1. Concept 0") < written.index("2. Concept 1")
    # Prerequisites by NAME, not id: nobody can judge sequencing against "c1".
    assert "**Needs first:** Concept 1" in written
    assert "c1" not in written, "ids leaked into a document written for a human"
    # The fields the teaching spec exists for.
    assert "Learners wrongly believe:" in written
    assert "Concept 0 is the same as the thing before it." in written
    assert "Predict what happens to concept 0 when the input doubles." in written
    assert "42.5s" in written


def test_the_digest_numbers_the_concepts_in_teaching_order_not_storage_order() -> None:
    """The digest's whole premise is "is this the order you would teach it in", so it has to read
    the order assembly derived — not the order the nodes happen to sit in the list.

    Pinned with the two deliberately disagreeing, because in a chain built front-to-back they are
    identical and the test cannot tell which one the code used.
    """
    # Arrange — storage order is the exact reverse of teaching order.
    ordered = _good_graph(count=3)
    shuffled = ordered.model_copy(update={"nodes": list(reversed(ordered.nodes))})

    # Act
    written = digest(shuffled, elapsed_s=1.0)

    # Assert — numbering follows topo_order (Concept 0 first), not the reversed node list.
    assert written.index("1. Concept 0") < written.index("3. Concept 2")


def test_the_digest_says_so_when_a_concept_was_never_authored() -> None:
    """A concept with no spec still belongs on the map, but a digest that rendered it as a bare
    heading would read as "this concept needs nothing taught about it"."""
    # Arrange
    good = _good_graph(count=3)
    nodes = [good.nodes[0].model_copy(update={"teaching_spec": None}), *good.nodes[1:]]

    # Act
    written = digest(good.model_copy(update={"nodes": nodes}), elapsed_s=1.0)

    # Assert
    assert "authoring failed" in written
