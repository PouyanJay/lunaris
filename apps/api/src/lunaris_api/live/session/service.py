import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping
from contextlib import AbstractContextManager, ExitStack, nullcontext
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from lunaris_live.graph import ConceptGraph, IGraphStore
from lunaris_live.session import (
    IGrader,
    IInterviewer,
    IKnowledgeStore,
    ISessionStore,
    ISimRegistry,
    ITutor,
    ITutorDeltaSink,
    LearnerModel,
    PlacementNotAnswerableError,
    Session,
    SessionClock,
    SessionClosedError,
    SessionStatus,
    StaleAnswerError,
    TurnOutcome,
    open_placement,
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

from ..service import LiveGraphService
from .throttle import LiveSessionBudgetExhaustedError, LiveSessionThrottle
from .turn_beat import TurnBeat
from .turn_context import TurnContext

logger = structlog.get_logger()


def _absorb_detached_turn(task: "asyncio.Task[Session]", *, run_id: str, session_id: str) -> None:
    """Consume the result of a turn whose stream went away, logging a failure rather than letting it
    surface as a bare unretrieved-exception warning with nothing to correlate it to.

    The ids are passed explicitly and cannot ride contextvars: the turn runs in its own task, which
    snapshots the context at creation, so a binding made inside that task never reaches this
    callback — it runs back in the caller's context.
    """
    if task.cancelled():
        return
    if (error := task.exception()) is not None:
        logger.warning(
            "live.session.detached_turn_failed",
            run_id=run_id,
            session_id=session_id,
            error=str(error),
        )


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
        sims: ISimRegistry | None = None,
        compiles: LiveGraphService | None = None,
        interviewer: IInterviewer | None = None,
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
        # None means this deployment mounts no simulators (T6), which is the default and which
        # leaves a sim-only concept exactly where P2a left it: taught here, not checkable here.
        self._sims = sims
        # Ceiling on one session's whole spend, read from the ledger's rollup. 0 is uncapped; it is
        # a runaway guard, not a ration — the clock is what bounds an ordinary sitting.
        self._session_budget_usd = session_budget_usd
        # The compile plane and the interviewer, both needed only to open a session on a *topic*
        # (P2c). Optional so a service composed for a map it already has — every suite before P2c —
        # needs neither; ``start_placement`` refuses to run without them rather than half-opening.
        self._compiles = compiles
        self._interviewer = interviewer

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

        session = await self._open_and_save(
            lambda: open_session(
                graph,
                known,
                SessionClock(turn=1, elapsed_s=0.0, budget_s=self._session_budget_s),
                session_id=session_id,
                run_id=run_id,
                tutor=self._tutor,
                sims=self._sims,
            ),
            run_id=run_id,
            session_id=session_id,
            owner_id=owner_id,
        )

        # No explicit ids: this line rides the contextvars binding above, so the correlation test
        # proves propagation rather than proving they were threaded through by hand.
        logger.info("live.session.started", turn_count=len(session.turns))
        return session

    async def start_placement(
        self, topic: str, *, session_id: str, owner_id: str | None = None
    ) -> Session:
        """Open a session on a topic whose map does not exist yet, and ask the first question.

        Plan §6, made literal: the compile is launched under a graph id minted here, the session
        is born ``PLACING`` on that same id, and the learner is interviewed while the map is built.
        Nothing here waits for the compile — a later turn finds the map by re-reading the store
        (T2) — so a learner who reloads keeps their session and the compile keeps its slot until
        it is done, exactly as a dropped compile stream does.

        Two runs, on purpose (R5): the interview turn's and the compile's. They are different work,
        they fail differently, and a line in either has to be findable from the session — so the
        session id is bound *before* the compile task is created, and the task inherits it.

        Raises whatever admission raises, before any work; ``RuntimeError`` if this service was
        composed without a compile plane or an interviewer, which is a wiring fault, not a learner
        one.
        """
        if self._compiles is None or self._interviewer is None:
            raise RuntimeError("opening on a topic needs a compile plane and an interviewer")
        interviewer = self._interviewer
        run_id = uuid4().hex
        graph_id = uuid4().hex
        bind_run_id(run_id, graph_id=graph_id, session_id=session_id)
        logger.info("live.session.placing_started", topic=topic)

        # Before any work, and before the compile: a refused opening should cost a lookup, not a
        # three-minute compile. The compile's own admission runs next, inside ``launch``; a refusal
        # there raises before the session exists, and the opening it counted is the price of asking
        # (T8 owns whether that ratio is right).
        if self._throttle is not None:
            self._throttle.admit_open(owner_id)
        # Detached on purpose. Its context is a copy of this one, so ``session_id`` rides every
        # line the compile logs; ``_compile_and_save`` rebinds ``run_id`` to the compile's own.
        self._compiles.launch(topic, graph_id=graph_id, run_id=uuid4().hex, owner_id=owner_id)

        session = await self._open_and_save(
            lambda: open_placement(
                topic,
                graph_id=graph_id,
                session_id=session_id,
                run_id=run_id,
                interviewer=interviewer,
            ),
            run_id=run_id,
            session_id=session_id,
            owner_id=owner_id,
        )

        # No explicit ids: this line rides the contextvars binding above (the correlation test
        # proves propagation, not hand-threading).
        logger.info("live.session.placing", turn_count=len(session.turns))
        return session

    async def _open_and_save(
        self,
        opener: Callable[[], Coroutine[object, object, Session]],
        *,
        run_id: str,
        session_id: str,
        owner_id: str | None,
    ) -> Session:
        """The opening ceremony both openings share: keys, ledger, the first turn, the row.

        One function for the same reason ``_take_and_save`` is: the order here is a correctness
        decision, and a second copy is a second place to get it wrong. The credential scope has to
        wrap the opener, not merely be resolved before it: the model client is built on first use
        *inside* the tutor or the interviewer, and it reads the tenant's key off this contextvar.
        Without it a BYOK tenant is served on the platform's key — money spent on their behalf that
        they never authorized and cannot see. The ledger is drained even when the turn failed: a
        call that timed out after the tokens went out really spent them. And the row is written
        after the turn, deliberately: a session saved before its first words would be a resumable
        transcript with nothing in it if the tutor then failed.
        """
        credentials = await self._resolve_credentials(owner_id)
        cost = self._cost_scope(run_id=run_id, session_id=session_id, owner_id=owner_id)
        try:
            with self._credential_scope(credentials), enter_cost_scope(cost):
                session = await opener()
        finally:
            await self._drain(cost, run_id=run_id, session_id=session_id)
        await asyncio.to_thread(self._sessions.save, session, owner_id=owner_id)
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
        context = await self._ready(session_id, owner_id)
        return await self._take_and_save(
            context,
            answer,
            answering_seq=answering_seq,
            run_id=run_id,
            owner_id=owner_id,
            slot=self._turn_slot(session_id),
        )

    async def stream_answer(
        self,
        session_id: str,
        answer: str,
        *,
        run_id: str,
        owner_id: str | None = None,
        answering_seq: int | None = None,
    ) -> AsyncIterator[tuple[TurnBeat, str | Session]]:
        """The same turn as ``answer``, narrating itself as the tutor writes it (P2b T2).

        Yields ``(TurnBeat.DELTA, …)`` per fragment and one terminal ``(TurnBeat.SESSION, …)``.
        The turn itself is identical — same director, same grader, same belief moves, same rows —
        because a second implementation of the loop is a second thing that can be wrong about a
        learner. What differs is only when the words leave.

        ``run_id`` is passed *in* rather than minted: this run began in a browser and crossed a Node
        runtime to get here (R5), and an id made on this side would leave three runtimes' logs with
        no shared key.

        Deliberately **awaited before it yields anything**, like the compile stream and for the
        same reason: admission, the session read and the closed-session check all have to happen
        while the status line is still available. Deferred into the body they could only be said as
        a frame, which a surface reads as "the turn failed" rather than "we did not start one".

        Everything that can refuse the turn is settled before this returns (the budget, the
        session, the named turn, the session's single turn slot) because a refusal is only a status
        while the status line is still available; ``take_turn`` re-checks the loop's own invariants
        (closed, stale) so that this layer's checks can be about *how the refusal is said*.
        """
        bind_run_id(run_id, session_id=session_id)
        context = await self._ready(session_id, owner_id)
        if context.session.status is SessionStatus.CLOSED:
            # ``take_turn`` checks this too, and that check stays: it is the loop's own invariant.
            # This one exists so the refusal is a 409 rather than an error frame on a 200 — the same
            # sentence the REST surface gives, which is what ``failure_mapping`` exists to hold.
            # ``CLOSED`` by name, not "anything but active": a placing session was refused, in its
            # own words, by ``_ready`` before this line (P2c T1).
            raise SessionClosedError(f"session {session_id} has already closed")
        answering_seq = self._resolve_answering_seq(context, answering_seq)
        # ``put_nowait`` on an unbounded queue never blocks and never awaits, which is exactly what
        # ``ITutorDeltaSink`` asks of a sink: the tutor must never wait on the surface reading it.
        queue: asyncio.Queue[str] = asyncio.Queue()
        taking = self._claim_slot_task(
            session_id,
            self._take_and_save(
                context,
                answer,
                answering_seq=answering_seq,
                run_id=run_id,
                owner_id=owner_id,
                on_delta=queue.put_nowait,
                # The slot is already ours (below), so the turn is told not to claim one.
                slot=nullcontext(),
            ),
        )
        return self._beats(taking, queue, run_id=run_id, session_id=session_id)

    @staticmethod
    def _resolve_answering_seq(context: TurnContext, answering_seq: int | None) -> int:
        """The turn this answer is for: the one the client named, checked, or the standing one.

        A client that names its turn (T9: the browser puts it in ``forwardedProps``) is refused
        *here* when that turn has moved on, so a late answer to a card the thread still shows is a
        409 in REST's words rather than a turn graded against whatever question is up now. A client
        that names nothing, which is every AG-UI client written before T9 and a bare reload, is
        answering the standing turn, derived exactly as T2 derived it. ``take_turn`` checks the seq
        again as the loop's own invariant; this check exists so the refusal is a status.
        """
        turns = context.session.turns
        standing_seq = turns[-1].seq if turns else 0
        if answering_seq is None:
            return standing_seq
        if answering_seq != standing_seq:
            raise StaleAnswerError(
                f"answer names turn {answering_seq}; {context.session.session_id} is on turn "
                f"{standing_seq}"
            )
        return answering_seq

    def _claim_slot_task(
        self, session_id: str, turn: Coroutine[None, None, Session]
    ) -> "asyncio.Task[Session]":
        """Claim this session's turn slot, then run the turn as a task that releases it on exit.

        Claimed *before* the task, so ``LiveSessionBusyError`` is raised while the status line is
        still available: claimed inside the task, a duplicate send got a 200 whose stream then
        apologised, in different words from the 409 the REST surface gives the same double send.
        Held in an ``ExitStack`` so something other than a ``with`` block can release it.

        Released from the task's done-callback, however the turn ends, and bound to the *task*
        rather than threaded through the coroutine. That is deliberate and it was learned by
        mutation: a held slot that only the coroutine referenced was released by garbage collection
        the moment the reference was dropped (the suspended ``taking_turn`` generator's ``finally``
        runs when it is collected), at a moment that differed from run to run. Bound here, the claim
        lives exactly as long as the turn, whatever the coroutine does with its arguments.
        """
        held = ExitStack()
        taking: asyncio.Task[Session] | None = None
        try:
            held.enter_context(self._turn_slot(session_id))
            taking = asyncio.create_task(turn)
            taking.add_done_callback(lambda _: held.close())
        except BaseException:
            # Nothing will run to release the slot, so release it here: a slot held by a turn that
            # never started would refuse every answer this session ever sends again. And a turn
            # that was built and never started (the busy refusal, every time) is closed rather than
            # dropped, or it is reported at collection as "never awaited".
            held.close()
            if taking is None:
                turn.close()
            raise
        return taking

    async def _beats(
        self,
        taking: "asyncio.Task[Session]",
        queue: "asyncio.Queue[str]",
        *,
        run_id: str,
        session_id: str,
    ) -> AsyncIterator[tuple[TurnBeat, str | Session]]:
        """The stream's body: each fragment as it lands, then the session the turn produced.

        **No fragment can be left behind, and the loop's shape is what guarantees it** rather than a
        drain at the end. ``asyncio.wait`` gives every future it is handed a slice before returning,
        so a pending ``queue.get()`` always resolves while the queue has anything in it — which
        means the "the turn is over" branch below is only reached with the queue genuinely empty,
        and nothing can be put into it between that moment and the check (no await separates them).

        Worth stating because the obvious defence — draining the queue after the task completes — is
        unreachable code here, and unreachable code that looks like a safety net is worse than none:
        it invites the belief that the loop is safe *because of it*. Proven by mutation: removing a
        drain from this position changed no test, and by ``test_no_fragment_is_lost_when_the_turn_
        finishes_before_anyone_reads_it``, which drives the case it was meant to cover.
        """
        fragment = asyncio.ensure_future(queue.get())
        try:
            while True:
                await asyncio.wait({fragment, taking}, return_when=asyncio.FIRST_COMPLETED)
                if fragment.done():
                    yield TurnBeat.DELTA, fragment.result()
                    fragment = asyncio.ensure_future(queue.get())
                    continue
                # The turn is over and the queue is empty (see above). Raises here if the turn
                # failed, which is what puts a ``RUN_ERROR`` on the stream.
                yield TurnBeat.SESSION, taking.result()
                return
        finally:
            # Unconditionally, and that is the point: the pending ``queue.get()`` is an
            # *independent* task, so a consumer that walks away mid-stream — a closed tab, an ASGI
            # cancellation, an ``aclose()`` — abandons this coroutine while that task is still
            # parked on the queue's getters. Cancelling only on the way out below would leave
            # it there until something resolved it, or until it was collected while still pending —
            # a "Task was destroyed but it is pending!" warning nobody can trace.
            fragment.cancel()
            if not taking.done():
                # The learner navigated away or the connection dropped. The turn is deliberately NOT
                # cancelled: it has already paid a grader and a tutor, and it persists the session
                # at the end — so re-reading is free recovery, and cancelling would bill somebody
                # for a turn nobody can get back. Phase 1 settled this for the compile stream.
                logger.info("live.session.stream_detached", run_id=run_id, session_id=session_id)
                taking.add_done_callback(
                    lambda task: _absorb_detached_turn(task, run_id=run_id, session_id=session_id)
                )

    async def _ready(self, session_id: str, owner_id: str | None) -> TurnContext:
        """Everything a turn needs before it can be taken, in the order it should be paid for.

        Admission first: a session already over its ceiling should cost a rollup read rather than
        three store reads and a pair of billed model calls. Shared by both entry points, because a
        learner's session must not be admitted on different terms depending on which transport they
        reached it over.
        """
        await self._refuse_if_budget_spent(session_id, owner_id)
        session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
        if session.status is SessionStatus.PLACING:
            # Before the graph is read, because a placing session's map may not have landed yet:
            # read first, a learner answering the interview would be told the *session* was not
            # found (404) for the whole compile window. T1's honest refusal on both transports;
            # T2 turns this branch into the interview path and deletes the error.
            raise PlacementNotAnswerableError(f"session {session_id} is still placing")
        graph = await asyncio.to_thread(self._graphs.load, session.graph_id, owner_id=owner_id)
        known = await asyncio.to_thread(self._knowledge.load, session.graph_id, owner_id=owner_id)
        return TurnContext(
            session=session,
            graph=graph,
            known=known,
            credentials=await self._resolve_credentials(owner_id),
        )

    async def _take_and_save(
        self,
        context: TurnContext,
        answer: str,
        *,
        answering_seq: int,
        run_id: str,
        owner_id: str | None,
        slot: AbstractContextManager[None],
        on_delta: ITutorDeltaSink | None = None,
    ) -> Session:
        """One turn, metered, and both of its writes. The whole of what the two entry points share.

        Kept as one function rather than duplicated per transport for the reason the whole session
        plane is built on: the order of these two writes is a correctness decision (see ``answer``),
        and a second copy is a second place for that order to be got wrong.

        The four things read at the top of a turn arrive as one ``TurnContext`` rather than as four
        arguments: they are read together, they are used together, and passing them apart meant both
        call sites destructured a tuple only to hand its parts straight back.

        ``slot`` is how the caller says who claims the session's turn slot: the REST path hands in
        the slot itself, so it is claimed here (the whole call is awaited inline, so a refusal is a
        status either way); the stream has already claimed it, because a busy refusal there must be
        a status too and the status line is gone by the time this task runs, and hands in a no-op.
        Required rather than defaulted, so a new entry point has to say which it is.

        The slot covers the **whole** turn, writes included, not only the billed calls. Released
        after the model calls alone it was free during the ledger drain and the two store writes,
        and a retry arriving then read the *old* head, passed every check made against it, found the
        slot free, and paid a second grader and tutor for the same turn before losing the
        compare-and-set (found by review in P2b T9, and reproduced: the retry even won the write).
        """
        session = context.session
        cost = self._cost_scope(run_id=run_id, session_id=session.session_id, owner_id=owner_id)
        # The slot is what makes the ceiling mean anything. Two answers sent at once both load the
        # same session, both pass every check made against that snapshot, and both pay a grader
        # and a tutor before either tries to write, and the ceiling cannot see spend that has not
        # been drained yet. The compare-and-set on the write settles which answer *counts*; only
        # this settles which one is *paid for*.
        with slot:
            try:
                with self._credential_scope(context.credentials), enter_cost_scope(cost):
                    outcome = await self._take(
                        session,
                        context.graph,
                        context.known,
                        answer,
                        answering_seq,
                        run_id,
                        on_delta=on_delta,
                    )
            finally:
                await self._drain(cost, run_id=run_id, session_id=session.session_id)
            # Conditional on the session still being the length this request read. Two answers in
            # flight at once both pass ``take_turn``'s check (they loaded the same head) and only
            # the store can settle which one lands. The loser is a stale answer, which is what the
            # learner is told (409), rather than a graded turn that quietly disappeared.
            await asyncio.to_thread(
                self._sessions.save,
                outcome.session,
                owner_id=owner_id,
                expect_turns=len(session.turns),
            )
            await asyncio.to_thread(self._knowledge.save, outcome.model, owner_id=owner_id)

        logger.info(
            "live.session.answered",
            run_id=run_id,
            session_id=session.session_id,
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
        *,
        on_delta: ITutorDeltaSink | None = None,
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
            sims=self._sims,
            run_id=run_id,
            elapsed_s=max(0.0, (datetime.now(UTC) - session.started_at).total_seconds()),
            budget_s=self._session_budget_s,
            on_delta=on_delta,
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
