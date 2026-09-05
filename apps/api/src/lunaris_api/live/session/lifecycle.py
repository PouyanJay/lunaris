import asyncio
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from lunaris_live.graph import IGraphStore
from lunaris_live.session import (
    DirectorMove,
    IKnowledgeStore,
    ISessionStore,
    MoveKind,
    Session,
    SessionClock,
    SessionStatus,
    SessionSummary,
    close_session,
    on_the_wall,
)
from lunaris_runtime.logging import bind_request_id

from ..work_refused import LiveWorkRefusedError
from .throttle import LiveSessionStillOpenError, LiveSessionThrottle

logger = structlog.get_logger()

#: The director's reason when the clock, rather than the learner or the material, ended it. Distinct
#: wording from the learner-asked close because a trace that read the same for both would lose the
#: only thing telling three different endings apart.
_TIME_UP = (
    "The session's minutes ran out while it was idle, so this is where it ends: what you covered, "
    "where it leaves you, and when to come back to it."
)

#: The statuses nothing more happens to.
_TERMINAL = frozenset({SessionStatus.CLOSED, SessionStatus.ABANDONED})


def _now() -> datetime:
    """The wall clock, in one place, so a listing and a session read agree about what "now" is."""
    return datetime.now(UTC)


def _elapsed_s(session: Session) -> float:
    """How long the session has been open, read off its row, never below zero.

    From the row rather than anything held in the process: a session outlives the request that
    opened it and every process that has served it since, and a clock that reset on a reload would
    let a learner extend a bounded session forever by refreshing.
    """
    return max(0.0, (_now() - session.started_at).total_seconds())


class SessionLifecycle:
    """Everything that happens to a session other than teaching it (review finding).

    Leaving, deleting, forgetting a topic, listing, and ending one whose clock ran out while nobody
    was looking. Its own collaborator because it changes for its own reasons: a new verb or a new
    terminal status has nothing to do with what a turn is, and ``LiveSessionService`` had accreted
    five unrelated jobs before this was pulled out of it.

    None of these call a model, resolve credentials or touch the cost scope, which is the seam:
    they are the operations that cost nothing and are owed to the learner anyway. The one exception
    is ``end``, which IS a turn (it writes a recap) and stays on the service beside the others.
    """

    def __init__(
        self,
        graphs: IGraphStore,
        sessions: ISessionStore,
        *,
        knowledge: IKnowledgeStore,
        session_budget_s: float,
        throttle: LiveSessionThrottle | None = None,
    ) -> None:
        self._graphs = graphs
        self._sessions = sessions
        self._knowledge = knowledge
        self._session_budget_s = session_budget_s
        self._throttle = throttle

    def _turn_slot(self, session_id: str) -> AbstractContextManager[None]:
        """This session's single in-flight turn, or a no-op when nothing is rationing turns."""
        return self._throttle.taking_turn(session_id) if self._throttle else nullcontext()

    async def discard(self, session_id: str, *, owner_id: str | None = None) -> Session:
        """Leave a session, without a ceremony (T3).

        Nothing is recapped, nothing is scheduled, and no model is called: leaving is not a teaching
        moment, and a learner who wants out gets out at no cost and with no words written at them on
        the way. The row is marked abandoned, which is its own status precisely so that a session
        somebody walked out of is never counted as one that ended well.

        Not a delete (U2). The transcript survives until the learner says otherwise, which is what
        makes deleting it a separate and deliberate act rather than a side effect of leaving.
        """
        bind_request_id(session_id, session_id=session_id)
        # Under the turn slot, though it pays for nothing. A discard writes unconditionally (there
        # is no answer to lose a compare-and-set to), so a turn landing after it would write the
        # session back to ACTIVE and bring a session the learner had just left back to life. The
        # slot makes leaving and teaching mutually exclusive; a learner who tries to leave mid-turn
        # is refused with "a turn is in flight" rather than silently ignored, which is the honest
        # half of a stop button that cannot cancel a call already paid for.
        with self._turn_slot(session_id):
            session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
            if session.status in _TERMINAL:
                return session
            return await self.abandon(session, owner_id=owner_id, run_id=None)

    async def abandon(
        self, session: Session, *, owner_id: str | None, run_id: str | None
    ) -> Session:
        """Mark a session abandoned and write it. No turn, no model call, no schedule."""
        left = session.model_copy(update={"status": SessionStatus.ABANDONED})
        await asyncio.to_thread(self._sessions.save, left, owner_id=owner_id)
        logger.info(
            "live.session.abandoned",
            run_id=run_id,
            session_id=session.session_id,
            turn_count=len(session.turns),
        )
        return left

    async def close_if_spent(self, session: Session, *, owner_id: str | None) -> Session:
        """End this session if its clock ran out while nobody was looking, and write it (T6).

        Named as the command it is rather than as the query it looks like (review finding): on the
        spent path it saves twice, and it is called from a read and from a listing.

        A Live session is bounded by design (plan §6), and that bound used to be noticed only from
        inside a turn: ``SessionClock.is_spent`` is read by ``decide_move``, which runs when a
        learner answers. Walk away and the row stayed ``active`` for ever. A bounded session that
        only notices its own bound when somebody acts is not bounded.

        Lazy rather than swept (U3): a look is what closes it, so there is no new deployed component
        and nothing that can silently stop running. The accepted cost is that a session nobody
        revisits keeps its stale status until something touches it.

        **Wordless, and therefore free.** A GET that spent money on a tutor call would be a
        surprising thing for a page load to do, and the words would be written for a learner who is
        not there. The schedule is still written and the meter is still built; only the prose is the
        plain one. A session whose map never landed is abandoned instead, for the reason ``end``
        gives: a ceremony about nothing is worse than no ceremony.

        Returns the session unchanged when it is terminal, inside its budget, or could not be
        closed. Never raises: this runs inside reads, and a session that cannot be ended tidily is
        not a reason to refuse a learner the transcript they asked for.
        """
        if session.status in _TERMINAL or _elapsed_s(session) < self._session_budget_s:
            return session
        run_id = uuid4().hex
        try:
            # The slot, for the third time in this journey and the same reason (AD15, AD17): this
            # write is unconditional, so a turn in flight either loses its own compare-and-set to
            # the goodbye written under it, or lands after and overwrites the goodbye. Busy means
            # somebody IS in this session, so it is not abandoned at all and the next look can
            # close it: a read must never fail because a tidy-up could not get a lock.
            with self._turn_slot(session.session_id):
                return await self._close_now(session, owner_id=owner_id, run_id=run_id)
        except LiveWorkRefusedError:
            return session

    async def _close_now(self, session: Session, *, owner_id: str | None, run_id: str) -> Session:
        """The close itself, with the slot already held. Never raises: this runs inside reads, and
        a session that cannot be ended tidily is not a reason to refuse a learner the transcript
        they asked for."""
        try:
            if session.status is not SessionStatus.ACTIVE:
                return await self.abandon(session, owner_id=owner_id, run_id=run_id)
            graph = await asyncio.to_thread(self._graphs.load, session.graph_id, owner_id=owner_id)
            model = await asyncio.to_thread(
                self._knowledge.load, session.graph_id, owner_id=owner_id
            )
            outcome = await close_session(
                session,
                graph,
                model,
                list(session.turns),
                DirectorMove(kind=MoveKind.CLOSE, reason=_TIME_UP),
                clock=on_the_wall(
                    SessionClock(
                        turn=len(session.turns) + 1,
                        elapsed_s=_elapsed_s(session),
                        budget_s=self._session_budget_s,
                    ),
                    session,
                ),
                # No words: see above.
                tutor=None,
                run_id=run_id,
            )
            await asyncio.to_thread(self._sessions.save, outcome.session, owner_id=owner_id)
            await asyncio.to_thread(self._knowledge.save, outcome.model, owner_id=owner_id)
        except Exception:
            # A map that has been purged, or a store having a bad minute. The session keeps its
            # stale status and the next look tries again; refusing the read instead would make a
            # tidy-up the reason a learner cannot see their own transcript.
            logger.warning(
                "live.session.expiry_close_failed",
                run_id=run_id,
                session_id=session.session_id,
                exc_info=True,
            )
            return session
        logger.info(
            "live.session.expired",
            run_id=run_id,
            session_id=session.session_id,
            turn_count=len(outcome.session.turns),
        )
        return outcome.session

    async def forget(self, graph_id: str, *, owner_id: str | None = None) -> None:
        """Clear what this learner has demonstrated about one map (T5).

        The other half of the delete pair (U2). Deleting a session is "stop keeping what I said";
        this is "forget what you concluded about me". Neither can do the other's job: beliefs are
        keyed by graph and node with no session id in them, and transcripts carry no beliefs.

        It is also the repair verb. A learner whose record was moved by a broken assessment surface
        keeps being taught around a belief nobody meant them to have, and without this the fix is
        invisible to everyone who already met the bug.

        **Refuses while a session on this map is still going**, rather than racing it. A session in
        progress holds the model in memory and writes it back at the end of every turn, so a reset
        underneath one would be silently undone by the next turn: the learner's clearing lost to a
        session they were still in. Refusing is both correct and the honest instruction, and the
        block is per map rather than per learner so one unfinished session cannot freeze every other
        topic.

        Silent when there is nothing to forget: a learner pressing it twice must not meet an error
        the second time.
        """
        bind_request_id(uuid4().hex, graph_id=graph_id)
        if await asyncio.to_thread(self._sessions.has_open_on, graph_id, owner_id=owner_id):
            raise LiveSessionStillOpenError(graph_id)
        if await self._turning_on(graph_id, owner_id=owner_id):
            raise LiveSessionStillOpenError(graph_id)
        await asyncio.to_thread(self._knowledge.forget, graph_id, owner_id=owner_id)
        logger.info("live.knowledge.forgotten", graph_id=graph_id)

    async def _turning_on(self, graph_id: str, *, owner_id: str | None) -> bool:
        """Whether a turn is in flight on any of this map's sessions (review finding).

        The status check above is not enough on its own, and the window it misses is narrow and
        real. A turn writes twice: the session row first, then the learner model. The session row is
        what flips to a terminal status, so between those two writes ``has_open_on`` already answers
        False while the model write is still to come — and a reset landing there is overwritten by
        it moments later. The learner's clearing undone by the very turn that ended their session,
        which is the exact failure AD18 exists to prevent, one turn later than AD18 looked.

        A turn holds its slot across **both** writes, so asking the throttle closes that window. It
        is asked per session because the slot is keyed by session and a reset is keyed by map.

        ⚠ In-process only: the throttle is per replica, so two replicas can still interleave. That
        is the same bound the turn slot itself has had since P2b, not a new weakness — but it means
        the honest fix, if Live ever runs multi-replica, is writing both rows in one transaction
        rather than a wider guard here.
        """
        if self._throttle is None:
            return False
        ids = await asyncio.to_thread(self._sessions.session_ids_on, graph_id, owner_id=owner_id)
        return any(self._throttle.is_taking_turn(session_id) for session_id in ids)

    async def delete(self, session_id: str, *, owner_id: str | None = None) -> None:
        """Remove a session, transcript and all (T4).

        The privacy verb. Everything a learner types is otherwise kept for ever, and the only way to
        be rid of it was to delete the auth user and let the cascade take it.

        **The transcript goes and nothing else (U2).** What the learner demonstrated lives in
        `live_knowledge`, keyed by graph and node with no session id in it, so a delete that tried
        to unpick "what this session taught them" would be guessing. Forgetting a topic is T5's own
        verb; a learner tidying their history must not silently lose the progress it earned them.

        Under the turn slot, though it pays for nothing: the store's save is an upsert on the id, so
        a turn landing after a delete would write the row straight back, and a learner's deleted
        transcript would be resurrected by a call that was already in flight when they pressed the
        button. The same guard a discard needs, for the same reason.

        Raises ``FileNotFoundError`` when there is no such session for this learner.
        """
        bind_request_id(session_id, session_id=session_id)
        with self._turn_slot(session_id):
            await asyncio.to_thread(self._sessions.delete, session_id, owner_id=owner_id)
        logger.info("live.session.deleted", session_id=session_id)

    async def recent(self, *, owner_id: str | None = None) -> list[SessionSummary]:
        """This learner's sessions, newest first (T2).

        The one session route that names no session, which is why it takes no ``session_id`` to
        correlate by and leaves the request's own id to do it. Summaries rather than sessions: a
        list of twenty would otherwise be twenty transcripts on the wire to draw twenty rows.
        """
        listed = await asyncio.to_thread(self._sessions.recent, owner_id=owner_id)
        # The list is the screen a learner meets an abandoned session on, so it is the one that has
        # to be truthful: a row reading "in progress" three days after the session ended is the
        # product lying about itself in the one place it summarises itself (T6). Only sessions this
        # page already named are touched, and only those whose clock has actually run out — which
        # in practice is none of them, because a look closes each one exactly once. The listing is
        # re-read rather than patched in place, so its ordering and timestamps stay the store's.
        if await self._close_the_spent(listed, owner_id=owner_id):
            listed = await asyncio.to_thread(self._sessions.recent, owner_id=owner_id)
        logger.info("live.session.listed", count=len(listed))
        return listed

    async def _close_the_spent(self, listed: list[SessionSummary], *, owner_id: str | None) -> bool:
        """End every session on this page whose time is up. True when anything changed.

        Each is loaded on its own because a summary is deliberately not enough to close from: the
        ceremony needs the transcript, the map and the beliefs. That cost is paid once per session
        ever, not once per listing, since a closed session is never a candidate again.
        """
        spent = [
            summary
            for summary in listed
            if summary.status not in _TERMINAL
            and (_now() - summary.started_at).total_seconds() >= self._session_budget_s
        ]
        changed = False
        for summary in spent:
            session = await asyncio.to_thread(
                self._sessions.load, summary.session_id, owner_id=owner_id
            )
            closed = await self.close_if_spent(session, owner_id=owner_id)
            changed = changed or closed.status is not session.status
        return changed
