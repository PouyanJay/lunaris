from datetime import timedelta

from .schema import Session, SessionClock


def on_the_wall(clock: SessionClock, session: Session) -> SessionClock:
    """The clock with its wall time filled from the session's own record, when the caller left it:
    the start it was born with plus the seconds since (P2c T6). One derivation, here, so no turn
    reads a wall clock of its own and a replayed session reads the same days it did."""
    if clock.at is not None:
        return clock
    return clock.model_copy(update={"at": session.started_at + timedelta(seconds=clock.elapsed_s)})
