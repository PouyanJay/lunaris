from typing import Protocol

from ...graph.schema import ConceptNode
from ..schema import DirectorMove


class ITutor(Protocol):
    """Turns a director's move into what the learner reads.

    The two halves of a turn are split here on purpose. The director is a *policy* and is
    deterministic by design (plan §7), so it can be exhaustively tested without a key; the tutor is
    generative and cannot be, so it sits behind a seam with a deterministic implementation for the
    offline path. Fusing them would make the policy untestable without a provider and the teaching
    unchangeable without touching the policy.

    ``move`` is passed whole rather than as a node plus a kind: the tutor teaches *this move on this
    concept*, and a remediation reads nothing like the introduction that already failed. It also
    means a fifth move kind cannot be added without every tutor being confronted with it.

    ``run_id`` is the turn's own run (R6), not the session's — a turn is one or more model calls,
    and what the tutor was asked has to be findable from a line in a stored transcript.
    """

    async def teach(
        self, move: DirectorMove, node: ConceptNode, *, topic: str, run_id: str
    ) -> str: ...
