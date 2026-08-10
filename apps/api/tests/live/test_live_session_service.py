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

from datetime import UTC, datetime, timedelta

import pytest
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.graph import ConceptGraph, MemoryGraphStore, StubGraphCompiler
from lunaris_live.session import (
    EvidenceKind,
    LearnerModel,
    MemoryKnowledgeStore,
    MemorySessionStore,
    Session,
    StubGrader,
    StubTutor,
    apply_evidence,
)
from lunaris_runtime.persistence import PersistenceError

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
        grader=StubGrader(),
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


async def test_the_transcript_is_written_before_the_belief() -> None:
    """Two writes, not one transaction, so the order is chosen for how each half fails.

    Transcript first means a crash between them under-counts evidence: the learner sees a graded
    turn whose belief did not move, and the concept comes round again. The other order looks safer
    and is not — the response is a retryable 503, a retry re-grades the same answer against a
    transcript that never recorded it, and one lucky guess plus a storage blip clears the mastery
    bar that ``_PULL`` was sized to keep two answers away.
    """
    # Arrange — a session store that reads back fine and refuses every write.
    graph = await _map()
    graphs, knowledge = MemoryGraphStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    opened = await LiveSessionService(
        graphs,
        MemorySessionStore(),
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    ).start("g1", session_id="s1", owner_id="learner-1")

    class RefusesToWrite:
        def save(
            self,
            session: Session,
            *,
            owner_id: str | None = None,
            expect_turns: int | None = None,
        ) -> None:
            raise PersistenceError("storage is having trouble")

        def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
            return opened

    service = LiveSessionService(
        graphs,
        RefusesToWrite(),
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    )

    # Act
    with pytest.raises(PersistenceError):
        await service.answer("s1", "I have no idea.", answering_seq=1, owner_id="learner-1")

    # Assert — the belief never landed, because the transcript never did.
    assert knowledge.load("g1", owner_id="learner-1").nodes == {}


async def test_a_clock_that_stepped_backwards_does_not_break_a_turn() -> None:
    """Hosts correct their clocks. If the machine answering a turn has stepped behind the one that
    opened the session, the elapsed time is negative — and ``SessionClock.elapsed_s`` is ``ge=0``,
    so the turn would fail on a validation error no handler translates and the learner would get a
    bare 500 for something entirely on our side."""
    # Arrange — a session stamped in the future, which is what a backward step looks like.
    graph = await _map()
    graphs, sessions, knowledge = MemoryGraphStore(), MemorySessionStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    service = LiveSessionService(
        graphs,
        sessions,
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    )
    opened = await service.start("g1", session_id="s1", owner_id="learner-1")
    sessions.save(
        opened.model_copy(update={"started_at": datetime.now(UTC) + timedelta(minutes=5)}),
        owner_id="learner-1",
    )

    # Act
    answered = await service.answer("s1", "An answer.", answering_seq=1, owner_id="learner-1")

    # Assert — the turn happened, treated as no time having passed.
    assert answered.turns[0].answer == "An answer."
