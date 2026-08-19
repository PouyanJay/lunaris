"""What the deterministic compiler guarantees, on both of ``IGraphCompiler``'s entry points.

The stub exists so the whole path runs offline and in CI, but it is a real implementation of the
protocol, and its ``extend`` already carries C1's structural obligations. Those are pinned here
rather than left until T5 wires the endpoint: the behaviour ships now, so it is tested now.
"""

from lunaris_live.graph import ConceptGraph, NodeProvenance, StubGraphCompiler


async def _compiled(topic: str = "How neural networks learn") -> ConceptGraph:
    return await StubGraphCompiler().compile(topic, graph_id="g1", run_id="r1")


async def test_a_compile_produces_a_teachable_chain() -> None:
    # Act
    graph = await _compiled()

    # Assert — a real graph shape, ordered, with the topic itself as the destination.
    assert graph.is_acyclic is True
    assert len(graph.nodes) >= 2
    assert graph.topo_order[-1] == graph.nodes[-1].id
    assert graph.version == 1


async def test_a_compile_is_reproducible_for_the_same_topic() -> None:
    """Stable ids: the same topic compiles to the same concepts, so two runs are diffable."""
    # Act
    first, second = await _compiled(), await _compiled()

    # Assert
    assert [node.id for node in first.nodes] == [node.id for node in second.nodes]


async def test_every_stub_concept_is_teachable_in_practice() -> None:
    """A node without teaching notes is teachable *in principle* and useless to a session: the
    tutor has a definition and nothing to teach around, and the grader (T5) has no criterion to
    stage. The offline path is what CI and keyless dev run, so a stub map that could not be taught
    would leave the whole session loop untested below the API.
    """
    # Act
    graph = await _compiled()

    # Assert
    for node in graph.nodes:
        assert node.teaching_spec is not None, f"{node.id} has no teaching notes"
        assert node.teaching_spec.objective
        assert node.teaching_spec.misconceptions, f"{node.id} names no misconception to teach past"
        assert node.mastery_criteria, f"{node.id} has nothing the learner could be asked to do"


async def test_every_compiled_node_is_marked_as_compiled() -> None:
    # Act
    graph = await _compiled()

    # Assert — provenance is what later tells a cold concept from one a learner asked for.
    assert {node.provenance for node in graph.nodes} == {NodeProvenance.COMPILED}


async def test_an_extension_attaches_to_its_anchors_and_bumps_the_version() -> None:
    # Arrange
    compiler = StubGraphCompiler()
    graph = await _compiled()
    anchor = graph.topo_order[0]

    # Act — the shape C1 needs: the learner asks for something mid-session, hung off what they know.
    extended = await compiler.extend(
        graph, request="Picking a learning rate", anchors=[anchor], run_id="r2"
    )

    # Assert
    assert extended.version == graph.version + 1
    added = next(node for node in extended.nodes if node.id not in {n.id for n in graph.nodes})
    assert added.requires == [anchor]
    assert extended.is_acyclic is True


async def test_an_extended_node_is_marked_as_extended() -> None:
    """The one thing a session must be able to tell apart later: what the compiler chose to teach
    versus what a learner's own question added."""
    # Arrange
    graph = await _compiled()

    # Act
    extended = await StubGraphCompiler().extend(
        graph, request="Picking a learning rate", anchors=[graph.topo_order[0]], run_id="r2"
    )

    # Assert
    added = next(node for node in extended.nodes if node.id not in {n.id for n in graph.nodes})
    assert added.provenance is NodeProvenance.EXTENDED
    assert all(node.provenance is NodeProvenance.COMPILED for node in graph.nodes)


async def test_an_extension_naming_an_unknown_anchor_still_assembles() -> None:
    """A runtime request can name something that isn't on the map; that must not corrupt it."""
    # Arrange
    graph = await _compiled()

    # Act
    extended = await StubGraphCompiler().extend(
        graph, request="Something else", anchors=["not-a-concept"], run_id="r2"
    )

    # Assert — the new concept lands as a starting point rather than dangling off nothing.
    added = next(node for node in extended.nodes if node.id not in {n.id for n in graph.nodes})
    assert added.requires == []
    assert extended.is_acyclic is True
    assert sorted(extended.topo_order) == sorted(node.id for node in extended.nodes)


async def test_an_extension_never_reuses_an_id_the_map_already_has() -> None:
    """The stub derives ids from the request text alone, so a learner echoing the topic back is
    enough to collide with a compiled concept.

    Two nodes under one id is silently destructive: ordering is derived over a set, so the duplicate
    collapses out of the order while both stay in the node list — and the bare new node shadows the
    compiled one's teaching notes for anything building an id lookup.
    """
    # Arrange — a request whose slug is exactly an existing concept's id.
    compiler = StubGraphCompiler()
    graph = await _compiled("How neural networks learn")
    colliding = graph.nodes[-1].id.replace("-", " ")

    # Act
    extended = await compiler.extend(graph, request=colliding, anchors=[], run_id="r2")

    # Assert — every concept keeps a distinct id, and the map stays internally consistent.
    ids = [node.id for node in extended.nodes]
    assert len(ids) == len(set(ids))
    assert len(extended.topo_order) == len(extended.nodes)


async def test_a_stub_map_stages_more_than_one_kind_of_do_statement() -> None:
    """P2b T10. The director's card rules key on the *kind* of criterion staged, and a map of
    nothing but EXPLAIN could never reach the criterion card through the real path. The second
    concept asks for a prediction; the first and the topic itself still ask to be explained back,
    so every earlier session test that echoes an explanation still lands where it did.
    """
    graph = await _compiled()

    kinds = [node.mastery_criteria[0].kind.value for node in graph.nodes]
    assert kinds == ["explain", "predict", "explain"]
    assert not any(
        criterion.needs_sim for node in graph.nodes for criterion in node.mastery_criteria
    )


async def test_a_hands_on_topic_ends_in_a_concept_only_a_simulator_can_check() -> None:
    """Opt-in by wording, deliberately: a session that ends on an uncheckable concept ends
    differently, and every earlier task's tests read the three-concept map. Asking for it puts a
    fourth concept after the topic itself with a single simulator-only criterion, which is what
    lets a stub session reach the concept-map card and, with a registry mounted, the simulator."""
    plain = await _compiled("Pendulums")
    hands_on = await _compiled("Hands-on with pendulums")

    assert len(plain.nodes) == 3
    assert len(hands_on.nodes) == 4
    practice = hands_on.nodes[-1]
    assert practice.requires == [hands_on.nodes[-2].id]
    assert all(criterion.needs_sim for criterion in practice.mastery_criteria)
    assert hands_on.topo_order[-1] == practice.id
