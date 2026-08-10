import asyncio

import structlog
from lunaris_live.graph import IGraphStore
from lunaris_live.session import ISessionStore, Session, open_session
from lunaris_runtime.logging import bind_run_id

logger = structlog.get_logger()


class LiveSessionService:
    """Opens and re-reads a learner's sessions.

    Orchestration only, like ``LiveGraphService``: mint the id, bind correlation, read the map, take
    the first turn, persist. What a turn *should* be is the director's and the tutor's business, and
    they arrive behind their own seams (T3, T4) without this changing.

    The graph is read fresh on every session, never cached: C1 grows a map at runtime, so a copy
    taken once would be stale the first time a learner asked something off it.
    """

    def __init__(self, graphs: IGraphStore, sessions: ISessionStore) -> None:
        self._graphs = graphs
        self._sessions = sessions

    async def start(
        self, graph_id: str, *, session_id: str, owner_id: str | None = None
    ) -> Session:
        """Open a session on ``graph_id`` and take its first turn.

        The id is minted by the router and passed *in* so it can ride a failure response as well as
        a success one — a learner reporting "it went wrong" needs to name the session precisely when
        it went wrong, which is the case a header set after the work would never cover.

        Raises ``FileNotFoundError`` when the learner has no such map — including when it is
        somebody else's, which is not-found rather than forbidden.
        """
        # Bound before any I/O: the graph id is known from the request, so deferring this only means
        # a hung read leaves no trace that the session was ever asked for.
        bind_run_id(session_id, graph_id=graph_id, session_id=session_id)
        logger.info("live.session.starting", graph_id=graph_id, session_id=session_id)

        # The stores are synchronous (supabase-py is), so keep the loop free while they work.
        graph = await asyncio.to_thread(self._graphs.load, graph_id, owner_id=owner_id)
        session = open_session(graph, session_id=session_id)
        await asyncio.to_thread(self._sessions.save, session, owner_id=owner_id)

        # No explicit ids: this line rides the contextvars binding above, so the correlation test
        # proves propagation rather than proving they were threaded through by hand.
        logger.info("live.session.started", turn_count=len(session.turns))
        return session

    async def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
        """Re-read a session so a reloaded tab lands back in it (U2).

        Correlated like the open: the resume path is the one U2 exists to make work, so a resume
        that fails must be as findable in the logs as an open that fails.
        """
        bind_run_id(session_id, session_id=session_id)
        session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
        logger.info("live.session.resumed", turn_count=len(session.turns))
        return session
