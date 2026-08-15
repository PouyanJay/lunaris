from typing import Protocol

from ...graph.schema import ConceptNode, MasteryCriterion
from ..schema import SimApp


class ISimRegistry(Protocol):
    """Which simulator, if any, can check this criterion on this concept.

    A **lookup**, deliberately: it takes a concept and a criterion and answers with a reference or
    with nothing. Everything about *building* a simulator — the contract, the builder agent, the
    Playwright verifier, the store (plan §9) — sits behind this method, which is what lets Phase 3
    replace the whole factory without the session loop noticing.

    ``None`` is the ordinary answer and will stay the ordinary answer for a long time: a map has
    many concepts and a factory builds sims one at a time. A concept with no simulator keeps P2a's
    honest position — taught here, not checkable here — rather than being handed an empty frame.

    Not async, and that is a constraint rather than an oversight. This is consulted while a turn is
    being assembled, in front of a learner who is waiting; a registry that needed to go to the
    network for it would put a second round trip inside every turn on a sim-bearing concept. Phase 3
    caches or preloads instead.
    """

    def app_for(self, node: ConceptNode, criterion: MasteryCriterion) -> SimApp | None: ...
