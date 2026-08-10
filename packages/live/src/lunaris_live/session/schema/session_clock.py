from pydantic import Field

from ...graph.schema.base import LiveModel


class SessionClock(LiveModel):
    """Where a session is in its own life — the third input to every decision.

    Two clocks, because they measure different things and the policy needs both. ``turn`` is the
    loop's own counter, and decay is measured in it so a session is reproducible: replaying the same
    answers gives the same beliefs. ``elapsed_s`` is the learner's wall clock, and it is what bounds
    the session (plan §6: 25-40 minutes) — a bound in turns would let a session of long, slow turns
    run for hours.
    """

    #: 1-based, monotonic. The turn about to be taken.
    turn: int = Field(ge=1)
    elapsed_s: float = Field(ge=0.0)
    #: The session's whole budget. Reaching it is a reason to close well, not to be cut off.
    budget_s: float = Field(gt=0.0)

    @property
    def is_spent(self) -> bool:
        return self.elapsed_s >= self.budget_s
