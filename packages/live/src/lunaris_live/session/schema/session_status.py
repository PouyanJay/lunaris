from enum import StrEnum


class SessionStatus(StrEnum):
    """Where a session is in its life. Bounded by design (plan §6: 25-40 minutes) — a session that
    could run forever has no shape a learner can feel, and no cost ceiling."""

    ACTIVE = "active"
    #: The director closed it deliberately. Distinct from abandoned: this one ended *well*.
    CLOSED = "closed"
