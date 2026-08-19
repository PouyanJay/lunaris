from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from ...graph.schema import ConceptNode, MasteryCriterion
from ..schema import Covered, DirectorMove, LessonParts


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

    ``profile`` is who this learner is, in a paragraph the placement interview produced (P2c T3):
    their background and what they want to be able to do. ``None`` when nothing is known — every
    session opened on a map — and never required, because a tutor that could not teach without it
    could not teach the sessions that have no interview.

    ``run_id`` is the turn's own run (R6), not the session's — a turn is one or more model calls,
    and what the tutor was asked has to be findable from a line in a stored transcript.

    **Two ways to say one thing (P2b A2).** ``teach`` answers with the whole turn and ``stream``
    answers with it in fragments; both must produce the same lesson from the same arguments, or a
    learner watching the live surface and a learner re-reading the stored session are being taught
    different things. They are separate methods rather than one built on the other because they fail
    differently: a whole answer can be retried transparently, and a stream whose socket dies after
    ten words has already put those ten words in front of somebody.
    """

    async def teach(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None,
        already_said: Sequence[str] = (),
        profile: str | None = None,
        run_id: str,
    ) -> str: ...

    def stream(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None,
        already_said: Sequence[str] = (),
        profile: str | None = None,
        run_id: str,
    ) -> AsyncIterator[str]:
        """The same lesson, in the order it is written.

        Declared ``def`` returning an ``AsyncIterator`` rather than ``async def``: an async
        generator function is *called* to get its iterator, not awaited, and an ``async def``
        signature here would type-check every correct implementation as wrong.
        """
        ...

    async def illustrate(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None,
        already_said: Sequence[str] = (),
        profile: str | None = None,
        run_id: str,
    ) -> LessonParts:
        """The material that goes *around* the lesson — Tier 2's generative half (P2b T5, U4).

        A worked example, a hint, and prompts to think through. What the tutor writes here is
        offered to ``compose_layout``, which decides which of it this learner actually sees and in
        what state. That split is the same line Tier 1 draws one tier up: the words are a model's,
        the arrangement is a rule's, and only the second one feeds the learner model.

        Same arguments as ``teach`` on purpose. The material has to belong to *this* move on *this*
        concept — a worked example written for an introduction is the wrong instrument for a
        remediation — and ``already_said`` is what stops the example reopening with the analogy the
        lesson already spent.

        **Nothing here can cost a turn.** Every field of ``LessonParts`` is optional, so an
        implementation that has no material, cannot reach a provider, or is asked for something it
        does not do answers with an empty one. The lesson and the Tier 1 card are on the turn
        already; a failed illustration costs the trimmings.
        """
        ...

    async def recap(
        self,
        topic: str,
        covered: Sequence[Covered],
        *,
        profile: str | None = None,
        run_id: str,
    ) -> str:
        """The close's words (P2c T5): a few sentences over what was covered and how it went.

        Briefed with the record (``covered`` is built deterministically from the transcript and
        the belief) and free only in how it says it; it can dress the record, never revise it. A
        recap that cannot be written raises ``TutorUnavailableError``, and the loop closes with a
        plain sentence instead: the ceremony is owed, the words are a nicety.
        """
        ...
