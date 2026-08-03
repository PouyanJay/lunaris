"""C2 — the three questions "follow the learner" has to be able to ask.

Phase 2 owns the director's *policy*. What Phase 1 owes it is the ability to answer, mid-turn and
cheaply: is what they just asked already on the map, what does it need first, and — failing both —
can I add it here (C1, done in T5).

If those queries don't exist, the director gets written as "next node in topological order", which
is a railway, and replacing that later is a rewrite rather than a patch. So they ship now, as pure
functions over a graph already in memory: no I/O, nothing to await, usable inside a single turn.
"""

from lunaris_live.graph import (
    ConceptGraph,
    ConceptNode,
    prerequisites_of,
    resolve_request,
)


def _node(node_id: str, name: str, *requires: str, aliases: list[str] | None = None) -> ConceptNode:
    return ConceptNode(
        id=node_id,
        name=name,
        definition=f"About {name.lower()}.",
        requires=list(requires),
        aliases=aliases or [],
    )


def _graph() -> ConceptGraph:
    return ConceptGraph(
        graph_id="g1",
        topic="How neural networks learn",
        nodes=[
            _node("slope", "Derivative as slope"),
            _node("loss", "Loss function", aliases=["cost function", "objective function"]),
            _node("gradient", "Gradient", "slope", "loss"),
            _node("descent", "Gradient descent step", "gradient"),
            _node("learning-rate", "Learning rate", "descent", aliases=["step size"]),
        ],
        topo_order=["loss", "slope", "gradient", "descent", "learning-rate"],
        is_acyclic=True,
    )


# ── resolve_request ───────────────────────────────────────────────────────────────────────────


def test_a_concept_named_outright_resolves_to_it() -> None:
    assert resolve_request(_graph(), "tell me about the learning rate").id == "learning-rate"


def test_a_paraphrase_resolves_by_meaning_rather_than_wording() -> None:
    """A learner does not use the compiler's vocabulary. Matching only exact names would send most
    real questions down the "not on the map" path and trigger a needless extension."""
    assert resolve_request(_graph(), "what's a cost function?").id == "loss"
    assert resolve_request(_graph(), "how big should the step size be").id == "learning-rate"


def test_matching_ignores_case_and_punctuation() -> None:
    assert resolve_request(_graph(), "GRADIENT DESCENT STEP!!").id == "descent"


def test_a_request_the_map_does_not_cover_resolves_to_nothing() -> None:
    """The signal that sends the director to C1's extension. A confident wrong match is worse than
    no match: the tutor would answer a question the learner did not ask."""
    assert resolve_request(_graph(), "how do transformers handle attention") is None


def test_a_request_made_only_of_common_words_resolves_to_nothing() -> None:
    """ "How does this work?" shares words with every concept and identifies none of them."""
    assert resolve_request(_graph(), "how does that work then") is None


def test_the_better_match_wins_when_several_concepts_share_a_word() -> None:
    # "gradient" alone is the concept; "gradient descent step" is the more specific one.
    assert resolve_request(_graph(), "explain the gradient").id == "gradient"
    assert resolve_request(_graph(), "explain the gradient descent step").id == "descent"


def test_resolving_against_an_empty_map_is_not_an_error() -> None:
    empty = ConceptGraph(graph_id="g1", topic="t")

    assert resolve_request(empty, "anything") is None


# ── prerequisites_of ──────────────────────────────────────────────────────────────────────────


def test_everything_a_concept_needs_first_comes_back_in_teaching_order() -> None:
    """Not just the direct prerequisites: the director needs the whole chain, because a learner who
    lacks the root lacks everything above it, and it needs them in an order it can teach."""
    # Act
    needed = prerequisites_of(_graph(), "learning-rate")

    # Assert — the full transitive closure, prerequisites before dependents.
    assert set(needed) == {"slope", "loss", "gradient", "descent"}
    assert needed.index("gradient") < needed.index("descent")
    assert needed.index("slope") < needed.index("gradient")


def test_a_starting_concept_needs_nothing() -> None:
    assert prerequisites_of(_graph(), "slope") == []


def test_only_the_relevant_branch_is_returned() -> None:
    """A concept's prerequisites are its own, not the whole graph before it."""
    assert set(prerequisites_of(_graph(), "gradient")) == {"slope", "loss"}


def test_asking_about_an_unknown_concept_returns_nothing() -> None:
    assert prerequisites_of(_graph(), "not-a-concept") == []


def test_the_order_matches_the_graphs_own_teaching_order() -> None:
    """Two answers about the same graph must not disagree about sequence."""
    graph = _graph()

    needed = prerequisites_of(graph, "learning-rate")

    assert needed == [node_id for node_id in graph.topo_order if node_id in set(needed)]


def test_a_concept_named_in_one_word_is_not_matched_by_any_passing_mention() -> None:
    """Single-word names are common ("Bias", "Momentum", "State"), and a bare word appearing
    anywhere in a sentence is not a question about that concept.

    This is the dangerous direction: a confident wrong match sends the tutor off to answer
    something the learner never asked, where a miss merely sends it to C1's extension.
    """
    # Arrange
    graph = ConceptGraph(
        graph_id="g1", topic="Statistics", nodes=[_node("bias", "Bias")], topo_order=["bias"]
    )

    # Assert — asked about, it resolves; mentioned in passing, it does not.
    assert resolve_request(graph, "explain bias") is not None
    assert (
        resolve_request(graph, "my own opinion has a bias in it, unrelated to any of this") is None
    )


def test_a_concept_whose_name_is_an_everyday_word_is_still_reachable() -> None:
    """ "Work" is a real physics concept. Stripping common words before matching would leave its
    name empty, so it could never resolve — and an on-map concept that always looks off-map would
    have the director extend the graph again and again for something already on it."""
    # Arrange
    graph = ConceptGraph(
        graph_id="g1", topic="Mechanics", nodes=[_node("work", "Work")], topo_order=["work"]
    )

    # Act / Assert
    assert resolve_request(graph, "what is work in physics").id == "work"


def test_an_inflected_word_is_a_known_miss() -> None:
    """Pinned rather than fixed: lexical matching has no stemming, so this returns None today.

    Recorded so the limitation is a documented choice rather than something Phase 2 discovers and
    reports as a regression — and so that swapping in embeddings, which would resolve it, shows up
    here as a deliberate change.
    """
    assert resolve_request(_graph(), "what are gradients") is None


def test_a_cyclic_hand_built_graph_terminates() -> None:
    """`assemble` guarantees acyclicity, but these are public functions anyone can call with a
    graph they built themselves — including, eventually, a director mid-turn."""
    # Arrange — a loop no assembly ever produced.
    cyclic = ConceptGraph(
        graph_id="g1",
        topic="t",
        nodes=[_node("a", "A", "b"), _node("b", "B", "a")],
        topo_order=[],
    )

    # Act / Assert — it returns rather than spinning, and reports the whole chain it found.
    assert set(prerequisites_of(cyclic, "a")) == {"a", "b"}


def test_a_prerequisite_missing_from_the_order_is_still_reported() -> None:
    """A partial chain that looks complete is the worst outcome: the caller cannot tell."""
    # Arrange — `c` is genuinely needed but absent from the recorded order.
    graph = ConceptGraph(
        graph_id="g1",
        topic="t",
        nodes=[_node("a", "A", "b"), _node("b", "B", "c"), _node("c", "C")],
        topo_order=["b", "a"],
    )

    # Act / Assert
    assert set(prerequisites_of(graph, "a")) == {"b", "c"}
