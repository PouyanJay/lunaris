from enum import StrEnum


class SessionStatus(StrEnum):
    """Where a session is in its life. Bounded by design (plan §6: 25-40 minutes) — a session that
    could run forever has no shape a learner can feel, and no cost ceiling."""

    #: Opened on a topic whose map is still compiling (P2c). The learner is being interviewed, not
    #: taught: nothing is staged, no belief moves, and the director has not decided anything yet.
    #: Its own status rather than ``ACTIVE`` with an empty map, because the two want different
    #: things from every surface — a placing session has no card to answer and no clock a learner
    #: can feel, and the transport tells the panel which by this value alone.
    PLACING = "placing"
    ACTIVE = "active"
    #: The director closed it deliberately. Distinct from abandoned: this one ended *well*.
    CLOSED = "closed"
