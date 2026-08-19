"""Opening a session: the director picks the first move, the tutor teaches it (Phase 2a, T4).

T1's skeleton opened on ``topo_order[0]`` with a fixed string, which was honest for a skeleton and
wrong for a product: it could not tell a learner returning to a map from one meeting it, and it said
the same thing either way. This is where the two real collaborators land — T3's policy and T4's
tutor — behind the same entry point, so nothing above has to know a session got smarter.
"""

from collections.abc import Sequence

import pytest
from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion
from lunaris_live.session import (
    DirectorMove,
    EvidenceKind,
    LearnerModel,
    LessonParts,
    MoveKind,
    SessionClock,
    StubTutor,
    apply_evidence,
    open_session,
)


def _graph() -> ConceptGraph:
    """A chain a → b, so "the first concept" and "the next one" are different answers."""
    return ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[
            ConceptNode(id="a", name="A", definition="The first idea."),
            ConceptNode(id="b", name="B", definition="Builds on A.", requires=["a"]),
        ],
        topo_order=["a", "b"],
        is_acyclic=True,
    )


def _clock() -> SessionClock:
    return SessionClock(turn=1, elapsed_s=0.0, budget_s=1800.0)


def _mastered(model: LearnerModel, node_id: str) -> LearnerModel:
    for turn in range(1, 4):
        model = apply_evidence(model, node_id, EvidenceKind.MET, at_turn=turn)
    return model


class SpyTutor:
    """Records what it was asked to teach; answers something the learner could read.

    ``already_said`` is accepted rather than omitted because ``ITutor`` declares it: a stub narrower
    than the protocol passes only for as long as no caller uses the part it left out, and opening a
    session now asks for Tier 2's material beside the words (T5).
    """

    def __init__(self) -> None:
        self.calls: list[tuple[DirectorMove, ConceptNode, str, str]] = []

    async def teach(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None = None,
        already_said: Sequence[str] = (),
        run_id: str,
    ) -> str:
        self.calls.append((move, node, topic, run_id))
        return f"Teaching {node.name}."

    async def illustrate(self, *args: object, **kwargs: object) -> LessonParts:
        """No material. The layout then degrades to the lesson and the card, which is what these
        tests are about — what the *tutor* was asked, not what was arranged around it."""
        return LessonParts()


async def test_a_returning_learner_does_not_start_over_at_the_root() -> None:
    """The whole reason T2 persists beliefs. A session that always opened on ``topo_order[0]``
    would be wired correctly and would re-teach somebody the thing they came back having already
    learned — which is the single fastest way to lose them."""
    # Arrange
    known = _mastered(LearnerModel(graph_id="g1"), "a")

    # Act
    session = await open_session(
        _graph(), known, _clock(), session_id="s1", run_id="r1", tutor=StubTutor()
    )

    # Assert — the director's answer, not the map's first entry.
    assert session.turns[0].move.node_id == "b"
    assert session.turns[0].move.kind is MoveKind.INTRODUCE


async def test_a_fresh_learner_still_opens_on_a_concept_with_nothing_before_it() -> None:
    """T1's guarantee, kept: whatever the policy becomes, a session may not open in the middle of
    the map. Phase 1's ordering exists so a learner is never shown a concept they cannot meet."""
    # Act
    session = await open_session(
        _graph(),
        LearnerModel(graph_id="g1"),
        _clock(),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )

    # Assert
    opened_on = session.turns[0].move.node_id
    assert next(node for node in _graph().nodes if node.id == opened_on).requires == []


async def test_the_tutor_teaches_the_concept_the_director_chose() -> None:
    """The two collaborators have to agree about the subject of a turn. If the tutor could be
    handed a different node than the move names, the transcript and the trace would be describing
    two different lessons (A2)."""
    # Arrange
    tutor = SpyTutor()
    known = _mastered(LearnerModel(graph_id="g1"), "a")

    # Act
    session = await open_session(
        _graph(), known, _clock(), session_id="s1", run_id="r1", tutor=tutor
    )

    # Assert
    move, node, topic, run_id = tutor.calls[0]
    assert node.id == move.node_id == session.turns[0].move.node_id
    assert topic == "A subject"
    assert run_id == "r1"


async def test_the_turn_the_learner_reads_is_the_tutors() -> None:
    # Act
    session = await open_session(
        _graph(),
        LearnerModel(graph_id="g1"),
        _clock(),
        session_id="s1",
        run_id="r1",
        tutor=SpyTutor(),
    )

    # Assert
    assert session.turns[0].tutor == "Teaching A."


async def test_a_turn_carries_the_run_that_produced_it() -> None:
    """R6: a session carries a ``session_id``, each turn carries a ``run_id``. A turn is now one or
    more model calls, and without the id on the turn there is no way to take a line out of a stored
    transcript and find what the tutor was actually asked."""
    # Act
    session = await open_session(
        _graph(),
        LearnerModel(graph_id="g1"),
        _clock(),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )

    # Assert — the turn's own id, not the session's.
    assert session.turns[0].run_id == "r1"
    assert session.session_id == "s1"


async def test_a_map_with_no_concepts_is_not_a_session() -> None:
    """Refused *here*, and asserted with a tutor that would teach anything.

    Both real tutors happen to refuse a CLOSE move themselves, so a test using one of them passes
    whether or not this function checks at all — which is how a guard that looks tested becomes
    dead code at the next refactor. The spy accepts every move, so only the check in
    ``open_session`` can produce this failure, and the untouched ``calls`` says it fired first.
    """
    # Arrange
    tutor = SpyTutor()

    # Act / Assert
    with pytest.raises(ValueError):
        await open_session(
            ConceptGraph(graph_id="g1", topic="A subject"),
            LearnerModel(graph_id="g1"),
            _clock(),
            session_id="s1",
            run_id="r1",
            tutor=tutor,
        )
    assert tutor.calls == [], "a map with nothing to teach must not cost a model call"


async def test_a_session_that_would_open_by_closing_is_refused() -> None:
    """A map whose teaching order names concepts it does not have leaves the director with nothing
    to introduce, so its first move is CLOSE. Handing a learner a session that opens on "we're
    done" is worse than telling the caller the map is broken."""
    # Arrange — an order that points at nothing real.
    broken = ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[ConceptNode(id="a", name="A", definition="The first idea.")],
        topo_order=["ghost"],
        is_acyclic=True,
    )
    tutor = SpyTutor()

    # Act / Assert
    with pytest.raises(ValueError):
        await open_session(
            broken,
            LearnerModel(graph_id="g1"),
            _clock(),
            session_id="s1",
            run_id="r1",
            tutor=tutor,
        )
    assert tutor.calls == []
