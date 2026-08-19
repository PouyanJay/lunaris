from collections.abc import AsyncIterator

from lunaris_live.session import Session

from ..turn_beat import TurnBeat


async def replayed_turn(session: Session) -> AsyncIterator[tuple[TurnBeat, str | Session]]:
    """The turn already in front of the learner, in the shape a live turn arrives in.

    What a freshly-loaded tab's first run gets. One fragment, because there is nothing to wait for:
    these words were written and stored some time ago, and pretending to type them out again would
    be an animation rather than a stream.

    Expressed as the same tagged stream a live turn produces so that the AG-UI frame sequence has
    exactly one definition (``turn_events``). A separate replay path would be a second contract for
    a client to be written against, and the two would drift the first time one of them gained a
    frame.

    A session with **no turns** yields no fragment at all. That state cannot come out of
    ``open_session``, which always teaches before it returns, but a stored row can be in it — and
    the message still opens and closes around the silence, because a client that has begun a run
    with no message to close simply waits.
    """
    if session.turns:
        yield TurnBeat.DELTA, session.turns[-1].tutor
    yield TurnBeat.SESSION, session
