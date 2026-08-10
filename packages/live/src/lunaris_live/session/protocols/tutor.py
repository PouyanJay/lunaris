from collections.abc import Sequence
from typing import Protocol

from ...graph.schema import ConceptNode, MasteryCriterion
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

    ``criterion`` is the do-statement this turn stages (U1): the tutor asks for it in its own
    words, the learner answers in prose, and a *separate* grader scores that answer against it.
    ``None`` means the concept has nothing a text session can check, so the tutor closes however it
    likes — and no belief can move from that turn.

    ``already_said`` is what this tutor has already told this learner about *this* concept in this
    session, oldest first. Without it "come at it a different way" is an instruction no tutor can
    follow: a second turn on one concept produced the first turn's words verbatim, which is the one
    thing a remediation must never be.

    ``run_id`` is the turn's own run (R6), not the session's — a turn is one or more model calls,
    and what the tutor was asked has to be findable from a line in a stored transcript.
    """

    async def teach(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None,
        already_said: Sequence[str] = (),
        run_id: str,
    ) -> str: ...
