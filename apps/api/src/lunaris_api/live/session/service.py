import asyncio
from uuid import uuid4

import structlog
from lunaris_live.graph import IGraphStore
from lunaris_live.session import (
    IGrader,
    IKnowledgeStore,
    ISessionStore,
    ITutor,
    Session,
    SessionClock,
    open_session,
    take_turn,
)
from lunaris_runtime.logging import bind_request_id, bind_run_id

logger = structlog.get_logger()


class LiveSessionService:
    """Opens and re-reads a learner's sessions.

    Orchestration only, like ``LiveGraphService``: mint the ids, bind correlation, read the map and
    what this learner already knows of it, take the turn, persist. What the turn *should* be belongs
    to the director and the tutor, which is why both arrive from outside rather than being built
    here.

    The graph is read fresh on every session, never cached: C1 grows a map at runtime, so a copy
    taken once would be stale the first time a learner asked something off it.
    """

    def __init__(
        self,
        graphs: IGraphStore,
        sessions: ISessionStore,
        *,
        knowledge: IKnowledgeStore,
        tutor: ITutor,
        grader: IGrader,
        session_budget_s: float,
    ) -> None:
        self._graphs = graphs
        self._sessions = sessions
        self._knowledge = knowledge
        self._tutor = tutor
        self._grader = grader
        self._session_budget_s = session_budget_s

    async def start(
        self, graph_id: str, *, session_id: str, owner_id: str | None = None
    ) -> Session:
        """Open a session on ``graph_id`` and take its first turn.

        The id is minted by the router and passed *in* so it can ride a failure response as well as
        a success one — a learner reporting "it went wrong" needs to name the session precisely when
        it went wrong, which is the case a header set after the work would never cover.

        Raises ``FileNotFoundError`` when the learner has no such map — including when it is
        somebody else's, which is not-found rather than forbidden. Raises
        ``TutorUnavailableError`` when the first turn could not be taught; nothing is persisted in
        that case, because a session whose first turn never happened is not a session.
        """
        # Two ids, because they answer different questions (R6): ``session_id`` is the learner's
        # whole session and ``run_id`` is the work of taking THIS turn. Both bound before any I/O —
        # the run is the reading and the teaching, not just the model call — so a hung read still
        # leaves a trace that the turn was attempted.
        run_id = uuid4().hex
        bind_run_id(run_id, graph_id=graph_id, session_id=session_id)
        logger.info("live.session.starting", graph_id=graph_id, session_id=session_id)

        # The stores are synchronous (supabase-py is), so keep the loop free while they work.
        graph = await asyncio.to_thread(self._graphs.load, graph_id, owner_id=owner_id)
        # What this learner already knows of this map (T2). Without it every session would open on
        # the map's first concept and re-teach a returning learner what they came back having
        # learned — the director cannot adapt to a model nobody read.
        known = await asyncio.to_thread(self._knowledge.load, graph_id, owner_id=owner_id)

        session = await open_session(
            graph,
            known,
            SessionClock(turn=1, elapsed_s=0.0, budget_s=self._session_budget_s),
            session_id=session_id,
            run_id=run_id,
            tutor=self._tutor,
        )
        # After the turn, deliberately: a session row written before the tutor spoke would be a
        # resumable transcript with nothing in it if the tutor then failed.
        await asyncio.to_thread(self._sessions.save, session, owner_id=owner_id)

        # No explicit ids: this line rides the contextvars binding above, so the correlation test
        # proves propagation rather than proving they were threaded through by hand.
        logger.info("live.session.started", turn_count=len(session.turns))
        return session

    async def answer(self, session_id: str, answer: str, *, owner_id: str | None = None) -> Session:
        """Score what the learner said, move what the system believes, and take the next turn.

        Two writes, not one transaction, and the order is chosen for how each half fails. The
        transcript goes first and the belief second, so a crash between them under-counts evidence
        rather than over-counting it: the learner sees a graded turn whose belief did not move, and
        the concept simply comes round again. The other order looks safer and is not — the response
        is a "try again" (503), a retry re-grades the same answer against a transcript that never
        recorded it, and ``apply_evidence`` runs twice on one answer. That is the one thing the
        ``_PULL`` / ``_MASTERED`` relationship exists to prevent: two pulls clear the mastery bar,
        so a single lucky guess plus a storage blip would unlock a dependent concept.

        Raises ``FileNotFoundError`` (no such session for this learner), ``SessionClosedError``
        (the director already ended it), and ``GraderUnavailableError`` / ``TutorUnavailableError``
        when the turn could not be taken at all — nothing has moved in that case, so a retry means
        exactly what the learner expects it to.
        """
        run_id = uuid4().hex
        bind_run_id(run_id, session_id=session_id)

        session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
        graph = await asyncio.to_thread(self._graphs.load, session.graph_id, owner_id=owner_id)
        known = await asyncio.to_thread(self._knowledge.load, session.graph_id, owner_id=owner_id)

        outcome = await take_turn(
            session,
            graph,
            known,
            answer=answer,
            grader=self._grader,
            tutor=self._tutor,
            run_id=run_id,
            budget_s=self._session_budget_s,
        )

        await asyncio.to_thread(self._sessions.save, outcome.session, owner_id=owner_id)
        await asyncio.to_thread(self._knowledge.save, outcome.model, owner_id=owner_id)

        logger.info(
            "live.session.answered",
            turn_count=len(outcome.session.turns),
            status=outcome.session.status.value,
        )
        return outcome.session

    async def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
        """Re-read a session so a reloaded tab lands back in it (U2).

        Correlated like the open: the resume path is the one U2 exists to make work, so a resume
        that fails must be as findable in the logs as an open that fails. As a *request* rather than
        a run, though — a resume takes no turn, and a ``run_id`` that was really a session id would
        undo the distinction the turns depend on.
        """
        bind_request_id(session_id, session_id=session_id)
        session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
        logger.info("live.session.resumed", turn_count=len(session.turns))
        return session
