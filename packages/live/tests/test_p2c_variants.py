"""Every move the director can make, and every way a session can end (Lunaris Live, P2c T9).

The journey's variant coverage: each ``MoveKind`` produced by the real path that produces it —
``place`` by an interview, ``introduce`` by an opening, ``retrieve`` by a review that has come due,
``remediate`` by two misses, ``close`` by the clock — and each close shape (the clock spent, the map
exhausted, the compile failed) ending the session properly: closed, said out loud with the reason,
with the meter and the schedule where there was a map to have them. Offline, deterministic, over
the package's own doors; the API suites hold the transport-specific shapes.
"""

from datetime import UTC, datetime, timedelta

import pytest
from _bayes_map import bayes_map, held
from lunaris_live.session import (
    LearnerModel,
    MoveKind,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
    StubGrader,
    StubInterviewer,
    StubPriorMapper,
    StubTutor,
    open_placement,
    open_session,
    settle_placement,
    take_turn,
)

_NOON = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
_BUDGET_S = 100.0


async def _opened(model: LearnerModel | None = None, *, at: datetime = _NOON):
    return await open_session(
        bayes_map("prior", "update"),
        model or LearnerModel(graph_id="g1"),
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S, at=at),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )


async def _answered(outcome, *, answer: str, elapsed_s: float):
    return await take_turn(
        outcome.session,
        bayes_map("prior", "update"),
        outcome.model,
        answer=answer,
        answering_seq=outcome.session.turns[-1].seq,
        grader=StubGrader(),
        tutor=StubTutor(),
        run_id=f"r{len(outcome.session.turns) + 1}",
        elapsed_s=elapsed_s,
        budget_s=_BUDGET_S,
    )


# ── every move ──────────────────────────────────────────────────────────────────────────────────


async def _turn_of(kind: MoveKind) -> SessionTurn:
    """The real path that produces each kind of move, and the turn it produced."""
    if kind is MoveKind.PLACE:
        placed = await open_placement(
            "Bayes' theorem",
            graph_id="g1",
            session_id="s1",
            run_id="r1",
            interviewer=StubInterviewer(),
        )
        return placed.turns[-1]
    if kind is MoveKind.INTRODUCE:
        return (await _opened()).session.turns[-1]
    if kind is MoveKind.RETRIEVE:
        due = held(LearnerModel(graph_id="g1"), "prior", due_at=_NOON - timedelta(days=1))
        return (await _opened(due)).session.turns[-1]
    if kind is MoveKind.REMEDIATE:
        outcome = await _opened()
        for elapsed_s in (10.0, 20.0):
            outcome = await _answered(outcome, answer="No idea.", elapsed_s=elapsed_s)
        return outcome.session.turns[-1]
    if kind is MoveKind.CLOSE:
        outcome = await _answered(await _opened(), answer="Anything.", elapsed_s=_BUDGET_S + 1)
        return outcome.session.turns[-1]
    raise AssertionError(f"no path produces {kind}")


@pytest.mark.parametrize("kind", list(MoveKind), ids=[kind.value for kind in MoveKind])
async def test_every_move_the_director_can_make_is_reached_and_reads_the_same_way(
    kind: MoveKind,
) -> None:
    """The invariants a reader of the transcript relies on, whichever move it is: the move is the
    one the path was built to produce, it says why, the tutor said something, and it names a
    concept exactly when it is about one (a placement and a close are about the session)."""
    turn = await _turn_of(kind)

    assert turn.move.kind is kind
    assert turn.move.reason.strip()
    assert turn.tutor.strip()
    assert (turn.move.node_id is None) == (kind in (MoveKind.PLACE, MoveKind.CLOSE))
    assert turn.run_id


# ── every close ─────────────────────────────────────────────────────────────────────────────────


async def _closed_by_the_clock() -> Session:
    outcome = await _answered(await _opened(), answer="Explain Prior.", elapsed_s=_BUDGET_S + 1)
    return outcome.session


async def _closed_by_exhaustion() -> Session:
    outcome = await _opened()
    for elapsed_s in (10.0, 20.0, 30.0, 40.0):
        standing = outcome.session.turns[-1]
        outcome = await _answered(outcome, answer=standing.criterion.statement, elapsed_s=elapsed_s)
        if outcome.session.status is SessionStatus.CLOSED:
            break
    return outcome.session


async def _closed_by_a_failed_compile() -> Session:
    placed = await open_placement(
        "Bayes' theorem", graph_id="g1", session_id="s1", run_id="r1", interviewer=StubInterviewer()
    )
    outcome = await settle_placement(
        placed,
        list(placed.turns),
        mapper=StubPriorMapper(),
        graph=None,
        failure="The compiler could not find enough on the subject.",
        model=LearnerModel(graph_id="g1"),
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=30.0,
        budget_s=_BUDGET_S,
    )
    assert outcome is not None
    return outcome.session


_CLOSES_WITH_A_MAP = {
    "clock spent": (_closed_by_the_clock, "minutes are up"),
    "map exhausted": (_closed_by_exhaustion, "Nothing on this map is left"),
}


@pytest.mark.parametrize("shape", list(_CLOSES_WITH_A_MAP), ids=list(_CLOSES_WITH_A_MAP))
async def test_every_close_with_a_map_ends_with_the_meter_and_the_schedule(shape: str) -> None:
    """Closed, said out loud with the reason a reader gets, on a CLOSE move, and the meter (with
    its schedule) beside the goodbye. A session that ended by going quiet would be indistinguishable
    from one that crashed (P2a AD22)."""
    close, says = _CLOSES_WITH_A_MAP[shape]

    session = await close()

    goodbye = session.turns[-1]
    assert session.status is SessionStatus.CLOSED
    assert goodbye.move.kind is MoveKind.CLOSE
    assert says in goodbye.tutor
    assert says in goodbye.move.reason
    assert goodbye.surface is not None and goodbye.surface.kind.value == "mastery_meter"
    assert goodbye.surface.entries, "something was graded, so the meter has it"
    assert all(entry.due_at is not None for entry in goodbye.surface.entries)


async def test_a_failed_compile_closes_the_session_without_a_map() -> None:
    """The one close with no map to have a meter of: closed, on a CLOSE move, naming the topic
    that never came and the compile's own reason, and no surface at all rather than an empty one."""
    session = await _closed_by_a_failed_compile()

    goodbye = session.turns[-1]
    assert session.status is SessionStatus.CLOSED
    assert goodbye.move.kind is MoveKind.CLOSE
    assert "could not find enough" in goodbye.tutor
    assert "could not find enough" in goodbye.move.reason
    assert goodbye.surface is None
    assert "Bayes' theorem" in goodbye.tutor, "the goodbye names the topic that never came"
