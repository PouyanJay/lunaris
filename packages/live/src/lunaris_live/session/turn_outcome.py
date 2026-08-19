from dataclasses import dataclass

from .schema import LearnerModel, Session


@dataclass(frozen=True)
class TurnOutcome:
    """What one turn of the loop produced: the session as it now reads, and the belief it moved.

    Both, because they are written to different places and must not drift: the session is a
    transcript row and the model is per-concept state keyed to the learner and the map. Returning
    them together makes it impossible to persist one and forget the other — which would show up as
    a learner whose transcript says they answered and whose director thinks they never did.

    A frozen dataclass rather than a Pydantic model: this never crosses the wire, it is a value the
    caller unpacks and throws away.
    """

    session: Session
    model: LearnerModel
    #: The concept whose prefetched first-turn material this turn used, if any (P2c T4), so the
    #: caller can let the store go of it: consumed once, generated fresh after.
    consumed_material: str | None = None
