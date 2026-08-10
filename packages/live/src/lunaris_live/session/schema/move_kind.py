from enum import StrEnum


class MoveKind(StrEnum):
    """What the director decided to do next — the plan's four moves (§7), and only these four.

    A closed set on purpose: the director is a *policy*, and a policy whose action space grows by
    accident is one nobody can reason about. Adding a fifth move should be a deliberate change here
    that every consumer of a trace is forced to notice.
    """

    #: Teach a concept the learner has not met, whose own prerequisites they have.
    INTRODUCE = "introduce"
    #: Come back to something learned earlier, before it decays past recall.
    RETRIEVE = "retrieve"
    #: The learner is stuck on the current concept — try it a different way.
    REMEDIATE = "remediate"
    #: Nothing left worth doing in this session, or the clock is spent.
    CLOSE = "close"
