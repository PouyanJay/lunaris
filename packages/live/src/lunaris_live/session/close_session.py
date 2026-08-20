import structlog

from ..graph import ConceptGraph
from .compose_layout import compose_layout
from .covered_in import covered_in
from .protocols import ITutor
from .recap_sentence import recap_sentence
from .schedule_reviews import schedule_reviews
from .schema import (
    DirectorMove,
    LayoutSpec,
    LearnerModel,
    LessonParts,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
    SurfaceSpec,
)
from .select_surface import select_surface
from .turn_outcome import TurnOutcome
from .tutor_unavailable_error import TutorUnavailableError

logger = structlog.get_logger()


async def close_session(
    session: Session,
    graph: ConceptGraph,
    model: LearnerModel,
    turns: list[SessionTurn],
    move: DirectorMove,
    *,
    clock: SessionClock,
    tutor: ITutor | None,
    run_id: str,
) -> TurnOutcome:
    """The session, ended with its ceremony (P2c T5): the meter of what was demonstrated beside
    where each concept stood at open (the delta), the recap over what was covered, and the
    director's reason. The surface is chosen from the same inputs the move was (T3), so a close
    shows what the learner did rather than an empty card.

    The schedule is written first (T6): every concept graded this session gets its next review
    date, and the meter and the recap read the scheduled model, so what the learner is shown is
    what the next session's director will honour — one model, not a shown one and a kept one.

    ``tutor=None`` closes it **without words**: the schedule is still written, the meter is still
    built, and the recap is the plain one. That is the close a session gets when nobody is present
    to be spoken to, which is what an expired session found by a page load actually is (journey
    live-session-lifecycle, T6). Free by construction rather than by luck: a GET that spent money
    on a tutor call would be a surprising thing for a page load to do. Everything that *matters*
    out of an ending survives it, because the meter and the schedule are computed from the record
    rather than written by a model."""
    assert clock.at is not None, "next_turn puts the clock on the wall before a close"
    model = schedule_reviews(model, graph, turns, at=clock.at)
    due = [known.due_at for known in model.nodes.values() if known.due_at is not None]
    logger.info(
        "live.session.reviews_scheduled",
        run_id=run_id,
        session_id=session.session_id,
        scheduled=len(due),
        next_review_at=min(due).isoformat() if due else None,
    )
    closing = select_surface(
        move,
        None,
        graph=graph,
        criterion=None,
        model=model,
        clock=clock,
        opening_beliefs=session.opening_beliefs,
    )
    ended = _closed(
        session,
        turns,
        move,
        run_id=run_id,
        recap=await _recap(tutor, session, graph, model, turns, run_id=run_id),
        surface=closing,
        # A goodbye names no concept and asked no tutor for material, so the lean layout is all
        # there is to arrange: the sign-off and the meter. Composed rather than left ``None`` so
        # that "every turn has a layout" is true of the last one too, and a renderer never has to
        # hold a second way of drawing a turn.
        layout=compose_layout(LessonParts(), node_id=None, model=model),
    )
    return TurnOutcome(session=ended, model=model)


async def _recap(
    tutor: ITutor | None,
    session: Session,
    graph: ConceptGraph,
    model: LearnerModel,
    turns: list[SessionTurn],
    *,
    run_id: str,
) -> str:
    """The recap in the tutor's words, or the plain sentence when it cannot speak (P2c T5).

    Briefed with the record (``covered_in``), which the tutor may dress and never revise. A tutor
    that cannot write it does not fail the close: the ceremony is owed and the words are a nicety,
    so the plain recap stands in and the failure is a warning worth seeing, not a session that
    ended in an error.
    """
    covered = covered_in(turns, graph, model)
    if tutor is None:
        # Nobody to speak to and nobody to pay for: the plain recap is the whole of the words.
        return recap_sentence(graph.topic, covered)
    try:
        return await tutor.recap(graph.topic, covered, profile=session.profile, run_id=run_id)
    except TutorUnavailableError:
        logger.warning(
            "live.session.recap_unavailable",
            run_id=run_id,
            session_id=session.session_id,
            exc_info=True,
        )
        return recap_sentence(graph.topic, covered)


def _closed(
    session: Session,
    turns: list[SessionTurn],
    move: DirectorMove,
    *,
    run_id: str,
    recap: str,
    surface: SurfaceSpec,
    layout: LayoutSpec,
) -> Session:
    """The session, ended — and said out loud.

    The goodbye is a turn rather than only a status, because ``status`` is a field and the
    transcript is what the learner reads: a session that ended by going quiet is indistinguishable
    from one that crashed. ``recap`` is the tutor's over the record, or the plain sentence (P2c
    T5); the director's own reason still closes it, verbatim, because the learner is owed the
    same explanation the trace gets and two wordings of one decision is how the two come to
    disagree.

    What is owed here is that a session which has run out of material or out of time stops rather
    than looping, ends visibly, says what it covered, and says why it stopped.
    """
    logger.info(
        "live.session.closed",
        run_id=run_id,
        session_id=session.session_id,
        reason=move.reason,
        turn_count=len(turns),
    )
    goodbye = SessionTurn(
        seq=len(turns) + 1,
        move=move,
        tutor=f"{recap.strip()} {move.reason}",
        run_id=run_id,
        surface=surface,
        layout=layout,
    )
    return session.model_copy(update={"turns": [*turns, goodbye], "status": SessionStatus.CLOSED})
