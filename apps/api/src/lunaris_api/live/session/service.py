import asyncio
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from lunaris_live.graph import ConceptGraph, IGraphStore
from lunaris_live.session import (
    IGrader,
    IKnowledgeStore,
    ISessionStore,
    ITutor,
    LearnerModel,
    Session,
    SessionClock,
    TurnOutcome,
    open_session,
    take_turn,
)
from lunaris_runtime.credentials import CredentialResolver, run_credentials
from lunaris_runtime.logging import bind_request_id, bind_run_id
from lunaris_runtime.metering import (
    CostScope,
    drain_cost_scope,
    enter_cost_scope,
    make_cost_scope,
)
from lunaris_runtime.persistence import ICostEventStore, ISubjectCostStore, PersistenceError
from lunaris_runtime.schema import CostSubjectType

from .throttle import LiveSessionBudgetExhaustedError, LiveSessionThrottle

logger = structlog.get_logger()

#: What the ledger is allowed to take out of a turn. Both are bounded for the same reason the
#: compile plane bounds its own: a store that *fails* is survivable — metering is observability and
#: the turn goes on — but a store that HANGS is worse than a failure, because it ties up the request
#: with no recovery path and nothing above it imposes a timeout. So a slow ledger costs telemetry,
#: never the answer a learner is waiting on.
_DRAIN_TIMEOUT_S = 2.0
_BUDGET_CHECK_TIMEOUT_S = 1.0


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
        cost_event_store: ICostEventStore | None = None,
        subject_cost_store: ISubjectCostStore | None = None,
        credential_resolver: CredentialResolver | None = None,
        throttle: LiveSessionThrottle | None = None,
        session_budget_usd: float = 0.0,
    ) -> None:
        self._graphs = graphs
        self._sessions = sessions
        self._knowledge = knowledge
        self._tutor = tutor
        self._grader = grader
        self._session_budget_s = session_budget_s
        # Both optional: metering is observability, and it is simply off when either store is
        # unwired (offline dev, the suite). A turn must never fail for want of a ledger.
        self._cost_event_store = cost_event_store
        self._subject_cost_store = subject_cost_store
        # None when BYOK is off — the tutor and grader then read the process environment.
        self._credential_resolver = credential_resolver
        # None leaves openings unrationed, which is what the suites predating this compose.
        self._throttle = throttle
        # Ceiling on one session's whole spend, read from the ledger's rollup. 0 is uncapped; it is
        # a runaway guard, not a ration — the clock is what bounds an ordinary sitting.
        self._session_budget_usd = session_budget_usd

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

        # Before any work: a refused opening should cost a lookup, not a tutor call.
        if self._throttle is not None:
            self._throttle.admit_open(owner_id)

        # The stores are synchronous (supabase-py is), so keep the loop free while they work.
        graph = await asyncio.to_thread(self._graphs.load, graph_id, owner_id=owner_id)
        # What this learner already knows of this map (T2). Without it every session would open on
        # the map's first concept and re-teach a returning learner what they came back having
        # learned — the director cannot adapt to a model nobody read.
        known = await asyncio.to_thread(self._knowledge.load, graph_id, owner_id=owner_id)

        credentials = await self._resolve_credentials(owner_id)
        cost = self._cost_scope(run_id=run_id, session_id=session_id, owner_id=owner_id)
        try:
            # The credential scope has to wrap the turn, not merely be resolved before it: the model
            # client is built on first use *inside* the tutor, and it reads the tenant's key off
            # this contextvar. Without it a BYOK tenant is taught on the platform's key — money
            # spent on their behalf that they never authorized and cannot see.
            with self._credential_scope(credentials), enter_cost_scope(cost):
                session = await open_session(
                    graph,
                    known,
                    SessionClock(turn=1, elapsed_s=0.0, budget_s=self._session_budget_s),
                    session_id=session_id,
                    run_id=run_id,
                    tutor=self._tutor,
                )
        finally:
            # Drained even when the turn failed: a tutor call that timed out after the tokens went
            # out really spent them, and a ledger recording only successes would under-report
            # exactly the runs somebody needs to go and look at.
            await self._drain(cost, run_id=run_id, session_id=session_id)
        # After the turn, deliberately: a session row written before the tutor spoke would be a
        # resumable transcript with nothing in it if the tutor then failed.
        await asyncio.to_thread(self._sessions.save, session, owner_id=owner_id)

        # No explicit ids: this line rides the contextvars binding above, so the correlation test
        # proves propagation rather than proving they were threaded through by hand.
        logger.info("live.session.started", turn_count=len(session.turns))
        return session

    async def answer(
        self, session_id: str, answer: str, *, answering_seq: int, owner_id: str | None = None
    ) -> Session:
        """Score what the learner said, move what the system believes, and take the next turn.

        Two writes, not one transaction, and the order is chosen for how each half fails. The
        transcript goes first and the belief second, so a crash between them under-counts evidence
        rather than over-counting it: the learner sees a graded turn whose belief did not move, and
        the concept simply comes round again. The other order looks safer and is not — the response
        is a "try again" (503), a retry re-grades the same answer against a transcript that never
        recorded it, and ``apply_evidence`` runs twice on one answer. That is the one thing the
        ``_PULL`` / ``_MASTERED`` relationship exists to prevent: two pulls clear the mastery bar,
        so a single lucky guess plus a storage blip would unlock a dependent concept.

        The session's age is measured from the row rather than from anything held in this process:
        a session outlives the request that opened it and every process that has served it since,
        and a clock that reset on a reload would let a learner extend a bounded session forever by
        refreshing.

        Raises ``FileNotFoundError`` (no such session for this learner), ``SessionClosedError``
        (the director already ended it), and ``GraderUnavailableError`` / ``TutorUnavailableError``
        when the turn could not be taken at all — nothing has moved in that case, so a retry means
        exactly what the learner expects it to.
        """
        run_id = uuid4().hex
        bind_run_id(run_id, session_id=session_id)

        # Admission first, and in this order: a session already over its ceiling should cost a
        # rollup read rather than two store reads and a pair of billed model calls.
        await self._refuse_if_budget_spent(session_id, owner_id)

        session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
        graph = await asyncio.to_thread(self._graphs.load, session.graph_id, owner_id=owner_id)
        known = await asyncio.to_thread(self._knowledge.load, session.graph_id, owner_id=owner_id)

        credentials = await self._resolve_credentials(owner_id)
        cost = self._cost_scope(run_id=run_id, session_id=session_id, owner_id=owner_id)
        try:
            # The slot is what makes the ceiling mean anything. Two answers sent at once both load
            # the same session, both pass every check made against that snapshot, and both pay a
            # grader and a tutor before either tries to write — and the ceiling cannot see spend
            # that has not been drained yet. The compare-and-set on the write settles which answer
            # *counts*; only this settles which one is *paid for*.
            with (
                self._turn_slot(session_id),
                self._credential_scope(credentials),
                enter_cost_scope(cost),
            ):
                outcome = await self._take(session, graph, known, answer, answering_seq, run_id)
        finally:
            await self._drain(cost, run_id=run_id, session_id=session_id)
        # Conditional on the session still being the length this request read. Two answers in
        # flight at once both pass ``take_turn``'s check — they loaded the same head — and only the
        # store can settle which one lands. The loser is a stale answer, which is what the learner
        # is told (409), rather than a graded turn that quietly disappeared.
        await asyncio.to_thread(
            self._sessions.save, outcome.session, owner_id=owner_id, expect_turns=len(session.turns)
        )
        await asyncio.to_thread(self._knowledge.save, outcome.model, owner_id=owner_id)

        logger.info(
            "live.session.answered",
            turn_count=len(outcome.session.turns),
            status=outcome.session.status.value,
        )
        return outcome.session

    def _turn_slot(self, session_id: str) -> AbstractContextManager[None]:
        """This session's single in-flight turn, or a no-op when nothing is rationing turns."""
        return self._throttle.taking_turn(session_id) if self._throttle else nullcontext()

    async def _take(
        self,
        session: Session,
        graph: ConceptGraph,
        known: LearnerModel,
        answer: str,
        answering_seq: int,
        run_id: str,
    ) -> TurnOutcome:
        """One turn of the loop, with the session's own clock read off its row.

        Clamped: ``SessionClock.elapsed_s`` is ``ge=0``, and a host whose clock steps backwards
        between opening a session and answering in it (an NTP correction, a container resync) would
        otherwise fail the turn on a validation error the router cannot translate. The same guard
        ``recall_of`` applies to its own elapsed count.
        """
        return await take_turn(
            session,
            graph,
            known,
            answer=answer,
            answering_seq=answering_seq,
            grader=self._grader,
            tutor=self._tutor,
            run_id=run_id,
            elapsed_s=max(0.0, (datetime.now(UTC) - session.started_at).total_seconds()),
            budget_s=self._session_budget_s,
        )

    def _cost_scope(
        self, *, run_id: str, session_id: str, owner_id: str | None
    ) -> CostScope | None:
        """This turn's cost scope, or ``None`` when metering is off.

        Keyed ``LIVE_SESSION`` and stated explicitly (D2): a session's id, a graph's and a course's
        are minted from independent sequences, so filing spend under the wrong namespace would
        eventually merge two subjects' totals in rows nobody may correct. The subject is the
        *session*, not the map it walks — a map outlives every sitting on it, and "what did this
        session cost" is a question about one sitting.
        """
        return make_cost_scope(
            self._cost_event_store,
            self._subject_cost_store,
            run_id=run_id,
            subject_type=CostSubjectType.LIVE_SESSION,
            subject_id=session_id,
            owner_id=owner_id,
        )

    async def _drain(self, cost: CostScope | None, *, run_id: str, session_id: str) -> None:
        """Persist what this turn spent. Never fatal: ``drain_cost_scope`` swallows its own
        failures, because a learner losing a turn to a slow ledger would be the telemetry costing
        more than it measures."""
        if cost is None:
            return
        try:
            async with asyncio.timeout(_DRAIN_TIMEOUT_S):
                await drain_cost_scope(cost, self._cost_event_store, self._subject_cost_store)
        except TimeoutError:
            # ``drain_cost_scope`` swallows its own failures but not its own duration. Losing the
            # row costs a line of telemetry; holding the turn open costs the learner their session.
            logger.warning(
                "live.session.cost_drain_timed_out", run_id=run_id, session_id=session_id
            )
            return
        logger.debug("live.session.cost_drained", run_id=run_id, session_id=session_id)

    async def _refuse_if_budget_spent(self, session_id: str, owner_id: str | None) -> None:
        """Stop a session that has reached its ceiling, before it spends past it.

        Read from the ledger's rollup rather than counted again in memory: the number already
        exists, and a second count would be a second truth. Fails **open** — a rollup that cannot
        be read refuses nobody, because a telemetry outage must not end somebody's lesson.
        """
        if self._subject_cost_store is None or self._session_budget_usd <= 0:
            return
        try:
            async with asyncio.timeout(_BUDGET_CHECK_TIMEOUT_S):
                spent = await self._subject_cost_store.get(
                    subject_type=CostSubjectType.LIVE_SESSION,
                    subject_id=session_id,
                    owner_id=owner_id,
                )
        except (PersistenceError, TimeoutError):
            logger.warning("live.session.budget_unreadable", session_id=session_id, exc_info=True)
            return
        if spent is not None and spent.total_amount >= self._session_budget_usd:
            logger.info(
                "live.session.budget_exhausted",
                session_id=session_id,
                spent=spent.total_amount,
                cap=self._session_budget_usd,
            )
            raise LiveSessionBudgetExhaustedError(spent.total_amount, self._session_budget_usd)

    async def _resolve_credentials(self, owner_id: str | None) -> Mapping[str, str] | None:
        """The owner's BYOK keys for this turn, or ``None`` to run on the process environment."""
        if owner_id is None or self._credential_resolver is None:
            return None
        return await self._credential_resolver(owner_id)

    @staticmethod
    def _credential_scope(
        credentials: Mapping[str, str] | None,
    ) -> AbstractContextManager[None]:
        """The turn's credential context: the tenant's keys when present, else a no-op (env
        fallback). Mirrors the compile plane's, so one tenant's key never outlives its request."""
        return run_credentials(credentials) if credentials else nullcontext()

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
