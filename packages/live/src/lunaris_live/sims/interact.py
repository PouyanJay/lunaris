from ..session.schema import Session, SessionStatus, SimAppCard
from ..session.stale_answer_error import StaleAnswerError
from ..session.tutor_unavailable_error import TutorUnavailableError
from .invalid_state import InvalidSimStateError
from .protocols.coach import ISimCoach
from .schema.event import SimEvent
from .schema.exchange import SimExchange


async def interact(
    session: Session, event: SimEvent, coach: ISimCoach, *, run_id: str
) -> tuple[Session, SimExchange]:
    """React without grading or advancing; callers serialize and persist this operation."""
    if session.status != SessionStatus.ACTIVE or not session.turns:
        raise StaleAnswerError("This session is not accepting simulator actions.")
    turn = session.turns[-1]
    surface = turn.surface
    if (
        turn.seq != event.turn_seq
        or turn.run_id != event.instance_id
        or turn.answer is not None
        or not isinstance(surface, SimAppCard)
        or surface.app_id != event.app_id
        or surface.contract is None
    ):
        raise StaleAnswerError("This simulator is no longer the active instrument.")
    try:
        surface.contract.validate_state(event.state)
    except ValueError as exc:
        raise InvalidSimStateError("Invalid simulator state.") from exc
    if event.sequence <= len(turn.sim_exchanges):
        previous = turn.sim_exchanges[event.sequence - 1]
        if previous.event == event:
            return session, previous
        raise StaleAnswerError("This simulator action has already been used.")
    if event.sequence != len(turn.sim_exchanges) + 1:
        raise StaleAnswerError("Reload the simulator before sending another action.")
    reaction = await coach.respond(surface.contract, event, run_id=run_id)
    try:
        surface.contract.validate_state(reaction.state)
    except ValueError as exc:
        raise TutorUnavailableError("The tutor returned an invalid simulator command.") from exc
    exchange = SimExchange(event=event, reaction=reaction, run_id=run_id)
    updated = turn.model_copy(update={"sim_exchanges": [*turn.sim_exchanges, exchange]})
    return session.model_copy(update={"turns": [*session.turns[:-1], updated]}), exchange
