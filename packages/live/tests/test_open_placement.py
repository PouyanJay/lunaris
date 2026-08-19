"""Opening a session on a topic, before the map exists (Lunaris Live, Phase 2c, T1).

Plan §6: the moment a topic arrives, the compile starts and the tutor opens a placement
conversation, so the learner never sees a progress bar. The session is therefore born *placing* —
on a graph id that has been minted but not yet compiled — and its first turn is a question about
the learner, not a lesson about a concept.

T1 is the walking skeleton: the shape of a placing session and the seam the interviewer speaks
through. The interview's bounds (T2), the priors it produces (T3) and the ceremony that closes a
session (T5 to T6) come later; what is pinned here is that a placement is a real ``Session`` — same
type, same store, same transcript — rather than a second kind of thing the surfaces would then have
to stitch to the first.
"""

from collections.abc import Sequence

from lunaris_live.session import (
    IInterviewer,
    InterviewExchange,
    MoveKind,
    SessionStatus,
    StubInterviewer,
    open_placement,
)


class SpyInterviewer:
    """Records what it was asked and answers a fixed opening question."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[InterviewExchange, ...], str]] = []

    async def ask(
        self,
        topic: str,
        *,
        exchanges: Sequence[InterviewExchange] = (),
        run_id: str,
    ) -> str | None:
        self.calls.append((topic, tuple(exchanges), run_id))
        return "What have you already met of this?"


async def test_a_placement_is_a_session_that_has_not_reached_its_map_yet() -> None:
    # Act
    session = await open_placement(
        "Bayes' theorem",
        graph_id="g-pending",
        session_id="s1",
        run_id="r1",
        interviewer=StubInterviewer(),
    )

    # Assert — the same Session type the loop persists, in a status of its own: a placing session
    # is neither active (nothing is being taught) nor closed (it has barely begun).
    assert session.status is SessionStatus.PLACING
    assert session.session_id == "s1"
    # The graph id is the one the compile was launched under, so a later turn can find the map by
    # re-reading the store rather than by holding process state.
    assert session.graph_id == "g-pending"
    # The topic rides the session: while placing there is no map to read it off, and a reload
    # mid-interview has to know what the interview is about.
    assert session.topic == "Bayes' theorem"


async def test_the_first_turn_is_the_interviewers_question_about_the_learner() -> None:
    # Arrange
    interviewer = SpyInterviewer()

    # Act
    session = await open_placement(
        "Bayes' theorem",
        graph_id="g-pending",
        session_id="s1",
        run_id="r1",
        interviewer=interviewer,
    )

    # Assert — one turn, a move of its own kind, about no concept (there are none yet), staging
    # nothing (an interview answer is not evidence, so nothing may grade it).
    (turn,) = session.turns
    assert turn.seq == 1
    assert turn.move.kind is MoveKind.PLACE
    assert turn.move.node_id is None
    assert turn.move.reason
    assert turn.tutor == "What have you already met of this?"
    assert turn.criterion is None
    assert turn.surface is None
    assert turn.run_id == "r1"
    # The interviewer was asked about THIS topic, with nothing yet exchanged: pinned by value.
    assert interviewer.calls == [("Bayes' theorem", (), "r1")]


async def test_the_stub_interviewer_opens_with_a_question_a_learner_can_answer() -> None:
    """The offline path has to be usable, not merely non-empty: `make run` without a key drives the
    surface through this interviewer."""
    interviewer: IInterviewer = StubInterviewer()

    question = await interviewer.ask("Bayes' theorem", run_id="r1")

    assert question is not None
    assert question.endswith("?")
    assert "Bayes' theorem" in question
