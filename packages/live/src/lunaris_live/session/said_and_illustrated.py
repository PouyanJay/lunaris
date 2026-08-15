import asyncio
from collections.abc import Sequence
from contextlib import suppress

import structlog

from ..graph import ConceptNode, MasteryCriterion
from .protocols import ITutor, ITutorDeltaSink
from .relay_delta import relay_delta
from .schema import DirectorMove, LessonParts

logger = structlog.get_logger()

#: How long the words will wait for the material once they are finished.
#:
#: The illustration is started *with* the lesson, so on a healthy turn this is never reached — by
#: the time a hundred words have been written a second call has usually long since answered. What
#: this bounds is the unhealthy case, and it is short on purpose: a learner who has read their
#: lesson should not sit in front of a finished turn waiting on a hint drawer. Tier 2 is allowed to
#: cost money and it is not allowed to cost time.
_GRACE_S = 2.0


async def said_and_illustrated(
    tutor: ITutor,
    move: DirectorMove,
    node: ConceptNode,
    *,
    topic: str,
    criterion: MasteryCriterion | None,
    already_said: Sequence[str],
    run_id: str,
    on_delta: ITutorDeltaSink | None = None,
) -> tuple[str, LessonParts]:
    """What the tutor says, and the material that goes around it — asked for at the same time.

    Concurrent rather than sequential, and that is the whole reason this function exists. Tier 2's
    material does not depend on the lesson's words (the layout holds a *slot* for them, never a
    copy), so the second call has no reason to start after the first finishes — and made sequential
    it would add its own latency to every turn for something the turn can go without.

    Two rules the arrangement enforces, both of them about what a failure costs:

    * **The words can fail the turn; the material cannot.** ``TutorUnavailableError`` from the
      lesson propagates — a turn with nothing said is not a turn. Anything from the illustration is
      swallowed into empty parts, because the layout degrades to prose and the card, which are on
      the turn already.
    * **Nothing is left running.** A lesson that dies cancels the illustration beside it, and an
      illustration still going when the words are done is given ``_GRACE_S`` and then cancelled.
      Both matter because the loser of either race holds a provider socket.

    ``on_delta`` selects the lesson's streaming path, exactly as it did before this ran beside
    anything (A2): passing one relays fragments as they are written, leaving it ``None`` is P2a's
    single call.
    """
    illustrating = asyncio.create_task(
        _illustrated(
            tutor,
            move,
            node,
            topic=topic,
            criterion=criterion,
            already_said=already_said,
            run_id=run_id,
        )
    )
    try:
        said = await _said(
            tutor,
            move,
            node,
            topic=topic,
            criterion=criterion,
            already_said=already_said,
            run_id=run_id,
            on_delta=on_delta,
        )
    except BaseException:
        # Including cancellation: the learner closed the tab, and a task nobody is waiting for would
        # otherwise keep a provider call alive behind them.
        #
        # Awaited after cancelling, not just signalled. ``cancel()`` only *requests* it, so
        # returning here would leave the claim above true on the next event-loop tick rather than
        # when this function returns — and a caller tearing down the loop immediately (a test, a
        # shutdown) is exactly when that gap is observable. Suppressed because the only thing this
        # can raise is the cancellation we just asked for.
        illustrating.cancel()
        with suppress(BaseException):
            await illustrating
        raise

    try:
        return said, await asyncio.wait_for(illustrating, _GRACE_S)
    except TimeoutError:
        # ``wait_for`` has already cancelled it. Logged rather than raised: the turn is complete and
        # what was lost is the trimmings, but a turn that keeps arriving bare is worth noticing.
        logger.warning(
            "live.tutor.illustration_late", run_id=run_id, node=node.id, grace_s=_GRACE_S
        )
        return said, LessonParts()


async def _illustrated(
    tutor: ITutor,
    move: DirectorMove,
    node: ConceptNode,
    *,
    topic: str,
    criterion: MasteryCriterion | None,
    already_said: Sequence[str],
    run_id: str,
) -> LessonParts:
    """The material, or none of it. The one place Tier 2's failures are turned into an absence.

    Swallowing here rather than at the call site is deliberate: an ``ITutor`` is a seam anyone can
    implement, and "illustration failures do not reach the loop" is a promise the loop has to keep
    about implementations it has never seen — including one that does not implement ``illustrate``
    at all, which is what the ``AttributeError`` branch covers.
    """
    try:
        return await tutor.illustrate(
            move,
            node,
            topic=topic,
            criterion=criterion,
            already_said=already_said,
            run_id=run_id,
        )
    except asyncio.CancelledError:
        # Never swallowed. This is the loop taking the task away, not the tutor failing, and
        # answering "no material" to a cancellation would leave the task looking like it finished.
        raise
    except Exception:
        logger.warning("live.tutor.illustration_failed", run_id=run_id, node=node.id, exc_info=True)
        return LessonParts()


async def _said(
    tutor: ITutor,
    move: DirectorMove,
    node: ConceptNode,
    *,
    topic: str,
    criterion: MasteryCriterion | None,
    already_said: Sequence[str],
    run_id: str,
    on_delta: ITutorDeltaSink | None,
) -> str:
    """What the tutor says, relayed fragment by fragment when somebody is listening.

    The two paths meet here and nowhere else, so the turn that gets stored is the same object either
    way. Relaying happens *inside* the loop over the fragments rather than after it — a version that
    collected the lesson and then replayed it would satisfy every assertion about content and leave
    the learner waiting exactly as long as P2a's surface did.
    """
    if on_delta is None:
        return await tutor.teach(
            move,
            node,
            topic=topic,
            criterion=criterion,
            already_said=already_said,
            run_id=run_id,
        )

    parts: list[str] = []
    async for delta in tutor.stream(
        move, node, topic=topic, criterion=criterion, already_said=already_said, run_id=run_id
    ):
        parts.append(delta)
        relay_delta(on_delta, delta)
    # Stripped for the same reason ``teach`` strips: a stored lesson opening or closing on
    # whitespace is a lesson that renders differently everywhere it is read.
    return "".join(parts).strip()
