"""The session plane below HTTP: what the service does with a learner's beliefs (Phase 2a, T4).

Nothing writes a belief through the API yet — the grader that does is T5 — so the claim that a
returning learner is met where they left off cannot be made through the endpoint. It is made here
instead, against the real stores and the real package, because the alternative is shipping the
knowledge read untested and discovering at T5 that the service was passing an empty model all along.

Owner scoping rides along rather than getting its own test here: the beliefs are stored under the
learner, so a service that read them unscoped would find an empty model and open at the root, which
is exactly what the first test would catch. The leak in the other direction — one learner reaching
another's map — is closed a layer earlier by the graph store, which refuses the read outright.
"""

import pytest
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.graph import ConceptGraph, MemoryGraphStore, StubGraphCompiler
from lunaris_live.session import (
    EvidenceKind,
    LearnerModel,
    MemoryKnowledgeStore,
    MemorySessionStore,
    StubTutor,
    apply_evidence,
)

_TOPIC = "How neural networks learn"


async def _map() -> ConceptGraph:
    return await StubGraphCompiler().compile(_TOPIC, graph_id="g1", run_id="r0")


def _mastering(graph: ConceptGraph, node_id: str) -> LearnerModel:
    """Beliefs as the grader will write them (T5): repeated met evidence on one concept."""
    model = LearnerModel(graph_id=graph.graph_id)
    for turn in range(1, 4):
        model = apply_evidence(model, node_id, EvidenceKind.MET, at_turn=turn)
    return model


@pytest.fixture
async def wired() -> tuple[LiveSessionService, ConceptGraph, MemoryKnowledgeStore]:
    graph = await _map()
    graphs, knowledge = MemoryGraphStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    service = LiveSessionService(
        graphs,
        MemorySessionStore(),
        knowledge=knowledge,
        tutor=StubTutor(),
        session_budget_s=1800.0,
    )
    return service, graph, knowledge


async def test_a_returning_learner_is_met_where_their_beliefs_left_them(
    wired: tuple[LiveSessionService, ConceptGraph, MemoryKnowledgeStore],
) -> None:
    # Arrange — they demonstrated the opening concept in an earlier session.
    service, graph, knowledge = wired
    knowledge.save(_mastering(graph, graph.topo_order[0]), owner_id="learner-1")

    # Act
    session = await service.start("g1", session_id="s1", owner_id="learner-1")

    # Assert — the next concept, not the one they already have.
    assert session.turns[0].move.node_id == graph.topo_order[1]


async def test_a_first_session_opens_at_the_start_of_the_map(
    wired: tuple[LiveSessionService, ConceptGraph, MemoryKnowledgeStore],
) -> None:
    """The other half of the same claim: with no beliefs stored, the director gets an empty model
    rather than a missing one, and the session opens where the map does."""
    # Arrange
    service, graph, _ = wired

    # Act
    session = await service.start("g1", session_id="s1", owner_id="learner-1")

    # Assert
    assert session.turns[0].move.node_id == graph.topo_order[0]


async def test_beliefs_stored_for_one_learner_are_not_read_for_another(
    wired: tuple[LiveSessionService, ConceptGraph, MemoryKnowledgeStore],
) -> None:
    """The knowledge read has to carry the owner through. Unscoped it would return an empty model
    here — harmless — but on a store where a stranger's row *could* match it would walk somebody
    past concepts they have never met, and it would look like the product working."""
    # Arrange — the beliefs belong to another learner entirely.
    service, graph, knowledge = wired
    knowledge.save(_mastering(graph, graph.topo_order[0]), owner_id="someone-else")

    # Act
    session = await service.start("g1", session_id="s2", owner_id="learner-1")

    # Assert
    assert session.turns[0].move.node_id == graph.topo_order[0]
