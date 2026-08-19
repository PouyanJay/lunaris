from enum import StrEnum


class MoveKind(StrEnum):
    """What the director decided to do next — the plan's four moves (§7), plus the one that comes
    before any of them.

    A closed set on purpose: the director is a *policy*, and a policy whose action space grows by
    accident is one nobody can reason about. ``PLACE`` was the deliberate fifth (P2c T1), and every
    consumer of a trace was made to notice: it is the move a session makes while its map is still
    compiling — a question about the learner, not a lesson about a concept — and it is the only
    move that is not the director's, because there is nothing yet for a director to decide over.
    """

    #: Teach a concept the learner has not met, whose own prerequisites they have.
    INTRODUCE = "introduce"
    #: Come back to something learned earlier, before it decays past recall.
    RETRIEVE = "retrieve"
    #: The learner is stuck on the current concept — try it a different way.
    REMEDIATE = "remediate"
    #: Nothing left worth doing in this session, or the clock is spent.
    CLOSE = "close"
    #: Ask the learner about themselves while the map compiles (plan §6, P2c). About no concept,
    #: stages nothing, moves no belief.
    PLACE = "place"
