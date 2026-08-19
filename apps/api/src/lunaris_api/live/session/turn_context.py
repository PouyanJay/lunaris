from dataclasses import dataclass

from lunaris_live.graph import ConceptGraph
from lunaris_live.session import LearnerModel, Session

#: The tenant's own model keys for this turn, or ``None`` to run on the process environment.
type TurnCredentials = dict[str, str] | None


@dataclass(frozen=True, slots=True)
class TurnContext:
    """Everything a turn needs, read once, before any of it is spent.

    The four reads at the top of a turn are one unit and were always used as one: the session, the
    map it walks, what this learner is believed to know of that map, and whose keys pay for it. They
    are gathered by ``LiveSessionService._ready`` and travel together — before this existed both
    entry points destructured the same tuple only to hand its five parts straight back to the
    function that needed them.

    A frozen dataclass rather than a Pydantic model because it never crosses a wire: it is a domain
    aggregate held inside Python for the length of one turn, which is exactly the line PYTHON.md
    draws between ``models/`` and ``schemas/``.
    """

    session: Session
    graph: ConceptGraph
    known: LearnerModel
    credentials: TurnCredentials
