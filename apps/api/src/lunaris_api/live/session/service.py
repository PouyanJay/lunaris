import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Mapping
from contextlib import AbstractContextManager, ExitStack, nullcontext
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from lunaris_live.graph import ConceptGraph, IGraphStore
from lunaris_live.session import (
    DEFAULT_MAX_QUESTIONS,
    DirectorMove,
    IGrader,
    IInterviewer,
    IKnowledgeStore,
    IMaterialStore,
    IPriorMapper,
    ISessionStore,
    ISimRegistry,
    ITutor,
    ITutorDeltaSink,
    LearnerModel,
    LessonParts,
    MoveKind,
    Session,
    SessionClock,
    SessionClosedError,
    SessionStatus,
    SessionSummary,
    StaleAnswerError,
    TurnOutcome,
    advance_placement,
    close_session,
    on_the_wall,
    open_placement,
    open_session,
    take_placement_turn,
    take_turn,
)
from lunaris_runtime.credentials import CredentialResolver, credentials_for, run_credentials
from lunaris_runtime.logging import bind_request_id, bind_run_id
from lunaris_runtime.metering import (
    CostScope,
    drain_cost_scope,
    enter_cost_scope,
    make_cost_scope,
)
from lunaris_runtime.persistence import ICostEventStore, ISubjectCostStore
from lunaris_runtime.schema import CostSubjectType

from ..service import LiveGraphService
from .material_prefetcher import MaterialPrefetcher
from .prefetch_registry import prefetch_registry
from .spent_past_ceiling import spent_past_ceiling
from .throttle import LiveSessionBudgetExhaustedError, LiveSessionThrottle
from .turn_beat import TurnBeat
from .turn_context import TurnContext

logger = structlog.get_logger()

#: The director's reason when the learner asked to finish. Read by a human auditing a session, so a
#: close somebody chose and a close the clock forced must not read identically.
_ASKED_TO_STOP = (
    "You asked to finish here, so this is the ending rather than an interruption: what you "
    "covered, where it leaves you, and when to come back to it."
)

#: The statuses nothing more happens to. Named once because two verbs and the loop all ask.
_TERMINAL = frozenset({SessionStatus.CLOSED, SessionStatus.ABANDONED})


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


def _elapsed_s(session: Session) -> float:
    """How long the session has been open, read off its row, never below zero.

    From the row rather than anything held in the process: a session outlives the request that
    opened it and every process that has served it since, and a clock that reset on a reload would
    let a learner extend a bounded session forever by refreshing. Clamped because
    ``SessionClock.elapsed_s`` is ``ge=0`` and a host whose clock steps backwards (an NTP
    correction, a container resync) would otherwise fail the turn on a validation error the router
    cannot translate — the same guard ``recall_of`` applies to its own elapsed count.
    """
    return max(0.0, (datetime.now(UTC) - session.started_at).total_seconds())


#: How much longer than the compile plane's own deadline a placing session waits for its map before
#: calling the compile lost (P2c T2). Generous on purpose: this fallback exists for a compile that
#: ran where this process cannot see it, and the cost of firing early is a session closed on a map
#: that was about to land.
_COMPILE_GRACE_S = 30.0


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
        mapper: IPriorMapper | None = None,
        compile_deadline_s: float = 0.0,
        compile_grace_s: float = _COMPILE_GRACE_S,
        interview_max_questions: int = DEFAULT_MAX_QUESTIONS,
        materials: IMaterialStore | None = None,
        prefetcher: MaterialPrefetcher | None = None,
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
        # Reads the finished interview against the map (P2c T3). ``None`` — a service composed for
        # a map it already has — never runs a placement, so it never needs one.
        self._mapper = mapper
        # How long a placing session waits for its map before calling the compile lost (P2c T2):
        # the compile plane's own deadline plus a grace, so this only ever fires when the compile
        # ran in a process this one cannot ask (a replica, a restart). 0 disables the fallback.
        self._compile_deadline_s = compile_deadline_s
        self._compile_grace_s = compile_grace_s
        self._interview_max_questions = interview_max_questions
        # First-turn material kept one node ahead (P2c T4), and the thing that asks for it. Both
        # optional: without them every turn asks for its material beside the lesson, as before.
        self._materials = materials
        self._prefetcher = prefetcher

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

        prefetched = await self._load_materials(graph_id, owner_id)
        opened = await self._open_and_save(
            lambda: open_session(
                graph,
                known,
                SessionClock(turn=1, elapsed_s=0.0, budget_s=self._session_budget_s),
                session_id=session_id,
                run_id=run_id,
                tutor=self._tutor,
                sims=self._sims,
                prefetched=prefetched,
            ),
            run_id=run_id,
            session_id=session_id,
            owner_id=owner_id,
        )
        session = opened.session
        self._materials_after(opened, graph, prefetched, owner_id=owner_id)

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
        if self._compiles is None or self._interviewer is None or self._mapper is None:
            raise RuntimeError(
                "opening on a topic needs a compile plane, an interviewer and a mapper"
            )
        interviewer = self._interviewer
        run_id = uuid4().hex
        graph_id = uuid4().hex
        bind_run_id(run_id, graph_id=graph_id, session_id=session_id)
        logger.info("live.session.placing_started", topic=topic)

        # Before any work, and before the compile: a refused opening should cost a lookup, not a
        # three-minute compile. Checked here and COUNTED after the compile is admitted (T8): a
        # topic-open consumes a compile slot and an opening, and it consumes both or neither — a
        # learner whose compile was refused (one already building) must not also have spent an
        # opening on nothing. Both gates are synchronous, so nothing slips between them.
        if self._throttle is not None:
            self._throttle.check_open(owner_id)
        # Detached on purpose. Its context is a copy of this one, so ``session_id`` rides every
        # line the compile logs; ``_compile_and_save`` rebinds ``run_id`` to the compile's own.
        # When the map lands, the root's material is asked for at once (P2c T4): "teaching begins
        # the moment the first node's materials exist" (plan §6), and the first lesson is full.
        self._compiles.launch(
            topic,
            graph_id=graph_id,
            run_id=uuid4().hex,
            owner_id=owner_id,
            on_landed=lambda graph: self._on_map_landed(session_id, graph, owner_id=owner_id),
        )
        if self._throttle is not None:
            # Counts (and re-checks: ``admit_open`` is the whole gate for ``start``, and a second
            # look at a synchronous counter is free), now that the compile has been admitted.
            self._throttle.admit_open(owner_id)

        async def placing() -> TurnOutcome:
            # An opening is a turn's outcome like any other; a placement's moves no belief and
            # consumes no material, so the outcome carries an empty model and nothing consumed.
            placed = await open_placement(
                topic,
                graph_id=graph_id,
                session_id=session_id,
                run_id=run_id,
                interviewer=interviewer,
            )
            return TurnOutcome(session=placed, model=LearnerModel(graph_id=graph_id))

        session = (
            await self._open_and_save(
                placing, run_id=run_id, session_id=session_id, owner_id=owner_id
            )
        ).session

        # No explicit ids: this line rides the contextvars binding above (the correlation test
        # proves propagation, not hand-threading).
        logger.info("live.session.placing", turn_count=len(session.turns))
        return session

    def _materials_after(
        self,
        outcome: TurnOutcome,
        graph: ConceptGraph | None,
        kept: Mapping[str, LessonParts],
        *,
        owner_id: str | None,
    ) -> None:
        """Let the store go of what this turn used, and ask for the next concept's (P2c T4).

        After the turn's real writes, and guarded: this is best-effort work on behalf of the *next*
        turn, and a fault in it must not turn a turn that has already been saved into a failure the
        learner sees (found in review). The prefetch itself is a task; what can raise here is only
        the scheduling — a store that cannot forget, a prediction that trips.
        """
        try:
            if self._materials is not None and outcome.consumed_material is not None:
                self._materials.forget(
                    outcome.session.graph_id, outcome.consumed_material, owner_id=owner_id
                )
            if outcome.session.status is not SessionStatus.ACTIVE or graph is None:
                return
            still_kept = {k: v for k, v in kept.items() if k != outcome.consumed_material}
            self._material_ahead(
                outcome.session, graph, outcome.model, still_kept, owner_id=owner_id
            )
        except Exception:
            logger.warning(
                "live.material.after_turn_failed",
                session_id=outcome.session.session_id,
                exc_info=True,
            )

    async def _load_materials(
        self, graph_id: str, owner_id: str | None
    ) -> Mapping[str, LessonParts]:
        """Everything kept for this map, or nothing when no store is wired."""
        if self._materials is None:
            return {}
        return await asyncio.to_thread(self._materials.load, graph_id, owner_id=owner_id)

    def _material_ahead(
        self,
        session: Session,
        graph: ConceptGraph,
        model: LearnerModel,
        kept: Mapping[str, LessonParts],
        *,
        owner_id: str | None,
    ) -> None:
        """One node ahead of where the session now is, if the prefetcher is wired."""
        if self._prefetcher is None or not session.turns:
            return
        current = session.turns[-1].move.node_id
        if current is None:
            return
        self._prefetcher.prefetch_ahead_of(
            session.session_id,
            graph,
            model,
            current=current,
            kept=kept,
            owner_id=owner_id,
            profile=session.profile,
        )

    def _on_map_landed(self, session_id: str, graph: ConceptGraph, *, owner_id: str | None) -> None:
        """The map has landed behind a placing session (called from the compile's done-callback):
        schedule the root's material, as work the prefetch registry holds and can be met at."""
        if self._prefetcher is None:
            return
        prefetch_registry().lead(self._root_material(session_id, graph, owner_id=owner_id))

    async def _root_material(
        self, session_id: str, graph: ConceptGraph, *, owner_id: str | None
    ) -> None:
        """The map has landed behind a placing session: ask for its root's material now.

        The root by teaching order, which is where an un-placed learner starts. A learner the
        interview then places past the root starts elsewhere (a boundary check, a deeper
        frontier), and this material waits unused until it is swept (T4's known approximation:
        the interview has not settled when the map lands, and waiting for it would forfeit the
        window that makes the first lesson full for everyone else). Guarded and logged: a task
        nobody awaits must not fail silently.
        """
        if self._prefetcher is None or not graph.topo_order:
            return
        try:
            kept = await self._load_materials(graph.graph_id, owner_id)
            self._prefetcher.prefetch_for_node(
                session_id, graph, graph.topo_order[0], kept=kept, owner_id=owner_id
            )
        except Exception:
            logger.warning(
                "live.material.root_prefetch_failed", session_id=session_id, exc_info=True
            )

    async def _open_and_save(
        self,
        opener: Callable[[], Coroutine[object, object, TurnOutcome]],
        *,
        run_id: str,
        session_id: str,
        owner_id: str | None,
    ) -> TurnOutcome:
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
        cost = self._cost_scope(run_id=run_id, session_id=session_id, owner_id=owner_id)
        try:
            scope = await credentials_for(self._credential_resolver, owner_id)
            with scope, enter_cost_scope(cost):
                opened = await opener()
        finally:
            await self._drain(cost, run_id=run_id, session_id=session_id)
        await asyncio.to_thread(self._sessions.save, opened.session, owner_id=owner_id)
        return opened

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
        session = await self._take_and_save(
            context,
            lambda: self._take(context, answer, answering_seq, run_id),
            run_id=run_id,
            owner_id=owner_id,
            slot=self._turn_slot(session_id),
        )
        assert session is not None, "an answered turn always writes"
        return session

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
            # The loop checks this too, and that check stays: it is the loop's own invariant.
            # This one exists so the refusal is a 409 rather than an error frame on a 200 — the same
            # sentence the REST surface gives, which is what ``failure_mapping`` exists to hold.
            raise SessionClosedError(f"session {session_id} has already closed")
        if context.session.status is SessionStatus.WARMING:
            # Same reasoning, same words as REST: nothing is open on a warming session (P2c T2).
            raise StaleAnswerError(f"nothing is open on session {session_id}; it is warming")
        answering_seq = self._resolve_answering_seq(context, answering_seq)
        # ``put_nowait`` on an unbounded queue never blocks and never awaits, which is exactly what
        # ``ITutorDeltaSink`` asks of a sink: the tutor must never wait on the surface reading it.
        queue: asyncio.Queue[str] = asyncio.Queue()
        taking = self._claim_slot_task(
            session_id,
            self._take_and_save(
                context,
                lambda: self._take(
                    context, answer, answering_seq, run_id, on_delta=queue.put_nowait
                ),
                run_id=run_id,
                owner_id=owner_id,
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
        if session.status in (SessionStatus.PLACING, SessionStatus.WARMING):
            # A placing session's map may not have landed yet, and that is not an error: it is the
            # state the interview exists to fill. Read the map if it is there, and ask the compile
            # plane whether it will ever be (P2c T2).
            graph = await self._graph_if_landed(session, owner_id)
            failure = None if graph is not None else self._map_failure(session)
        else:
            graph = await asyncio.to_thread(self._graphs.load, session.graph_id, owner_id=owner_id)
            failure = None
        known = await asyncio.to_thread(self._knowledge.load, session.graph_id, owner_id=owner_id)
        prefetched = await self._load_materials(session.graph_id, owner_id)
        return TurnContext(
            session=session,
            graph=graph,
            known=known,
            credentials=await self._resolve_credentials(owner_id),
            map_failure=failure,
            prefetched=prefetched,
        )

    async def _graph_if_landed(self, session: Session, owner_id: str | None) -> ConceptGraph | None:
        """The placing session's map, or ``None`` while the compile has not landed it."""
        try:
            return await asyncio.to_thread(self._graphs.load, session.graph_id, owner_id=owner_id)
        except FileNotFoundError:
            return None

    def _map_failure(self, session: Session) -> str | None:
        """Why a placing session's map will never come, or ``None`` while it still might.

        Two sources, because the compile may not have run here. The compile plane knows about a
        task it launched in this process (a failure with its own reason). Failing that, a compile
        that has been running longer than its own deadline plus a grace did not run in a process we
        can ask, or is lost — either way the learner should not be interviewed for a map that will
        not come, and the honest thing is to say so and stop.
        """
        if self._compiles is not None:
            reason = self._compiles.failure_of(session.graph_id)
            if reason is not None:
                return reason
        if self._compile_deadline_s <= 0:
            return None
        waited_s = (datetime.now(UTC) - session.started_at).total_seconds()
        if waited_s > self._compile_deadline_s + self._compile_grace_s:
            return "The map took too long to build."
        return None

    async def _take_and_save(
        self,
        context: TurnContext,
        take: Callable[[], Awaitable[TurnOutcome | None]],
        *,
        run_id: str,
        owner_id: str | None,
        slot: AbstractContextManager[None],
    ) -> Session | None:
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
                    outcome = await take()
            finally:
                await self._drain(cost, run_id=run_id, session_id=session.session_id)
            if outcome is None:
                # Nothing happened (a warming session polled before its map landed): nothing to
                # write, and the caller says so rather than pretending a turn was taken.
                return None
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
            if context.map_failure is not None and outcome.session.status is SessionStatus.CLOSED:
                # The close is on the row; the compile plane need not remember the failure for us.
                assert self._compiles is not None
                self._compiles.forget_failure(session.graph_id)
            self._materials_after(outcome, context.graph, context.prefetched, owner_id=owner_id)

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
        context: TurnContext,
        answer: str,
        answering_seq: int,
        run_id: str,
        *,
        on_delta: ITutorDeltaSink | None = None,
    ) -> TurnOutcome:
        """One turn of the loop, with the session's own clock read off its row.

        Two loops, one door (P2c T2): a placing session's answer goes to the interview, an active
        session's to the lesson. The clock is the same either way — the interview is inside the
        session's budget (A1) — and it is the row's (``_elapsed_s``).
        """
        session = context.session
        elapsed_s = _elapsed_s(session)
        if session.status in (SessionStatus.PLACING, SessionStatus.WARMING):
            assert self._interviewer is not None, "a placing session needs an interviewer"
            assert self._mapper is not None, "a placing session needs a prior mapper"
            return await take_placement_turn(
                session,
                answer=answer,
                answering_seq=answering_seq,
                interviewer=self._interviewer,
                mapper=self._mapper,
                graph=context.graph,
                failure=context.map_failure,
                model=context.known,
                tutor=self._tutor,
                run_id=run_id,
                elapsed_s=elapsed_s,
                budget_s=self._session_budget_s,
                on_delta=on_delta,
                sims=self._sims,
                prefetched=context.prefetched,
                max_questions=self._interview_max_questions,
            )
        assert context.graph is not None, "an active session always has its map"
        return await take_turn(
            session,
            context.graph,
            context.known,
            answer=answer,
            answering_seq=answering_seq,
            grader=self._grader,
            tutor=self._tutor,
            sims=self._sims,
            run_id=run_id,
            elapsed_s=elapsed_s,
            budget_s=self._session_budget_s,
            on_delta=on_delta,
            prefetched=context.prefetched,
        )

    async def advance(self, session_id: str, *, owner_id: str | None = None) -> Session | None:
        """Move a warming session on if its map has landed (or its compile has failed) — P2c T2.

        The way out of the honest wait: the surface polls this while a session is warming. Answers
        with the session when there was something to do (teaching began, or the session closed on a
        failed compile) — and also when the session is not warming at all, which a poll can meet
        when an answer got there first: the current row, unchanged. ``None`` means still warming,
        which the router says as a 202 rather than as a turn.

        Under the same slot, ceiling and ledger as a turn, because when it does something it IS a
        turn: the first lesson, taught and paid for.
        """
        run_id = uuid4().hex
        bind_run_id(run_id, session_id=session_id)
        context = await self._ready(session_id, owner_id)
        if context.session.status is not SessionStatus.WARMING:
            return context.session
        session = context.session
        assert self._mapper is not None, "a warming session needs a prior mapper"
        return await self._take_and_save(
            context,
            lambda: advance_placement(
                session,
                mapper=self._mapper,
                graph=context.graph,
                failure=context.map_failure,
                model=context.known,
                tutor=self._tutor,
                run_id=run_id,
                elapsed_s=_elapsed_s(session),
                budget_s=self._session_budget_s,
                sims=self._sims,
                prefetched=context.prefetched,
            ),
            run_id=run_id,
            owner_id=owner_id,
            slot=self._turn_slot(session_id),
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

        The reading is ``spent_past_ceiling``'s, shared with the prefetch (T8), so a session is
        refused a turn and refused material on the same number; what is this method's is the
        refusal — a status the learner reads, in ``failure_mapping``'s words.
        """
        spent = await spent_past_ceiling(
            self._subject_cost_store,
            session_id=session_id,
            owner_id=owner_id,
            ceiling_usd=self._session_budget_usd,
        )
        if spent is not None:
            logger.info(
                "live.session.budget_exhausted",
                session_id=session_id,
                spent=spent,
                cap=self._session_budget_usd,
            )
            raise LiveSessionBudgetExhaustedError(spent, self._session_budget_usd)

    async def _resolve_credentials(self, owner_id: str | None) -> Mapping[str, str] | None:
        """The owner's BYOK keys for this turn, or ``None`` to run on the process environment."""
        if owner_id is None or self._credential_resolver is None:
            return None
        return await self._credential_resolver(owner_id)

    @staticmethod
    def _credential_scope(
        credentials: Mapping[str, str] | None,
    ) -> AbstractContextManager[None]:
        """The turn's credential context: the tenant's keys when BYOK is on for them, else a no-op
        (env fallback). An EMPTY vault is a scope with nothing in it, not the env: a tenant who
        has set no keys must not be taught on the platform's (the compile plane's rule; the
        session plane read ``if credentials`` and let an empty vault fall through, found in T4)."""
        return nullcontext() if credentials is None else run_credentials(credentials)

    async def end(self, session_id: str, *, owner_id: str | None = None) -> Session:
        """Close a session because the learner asked to, with the ceremony intact (T3).

        The same ending the clock would have produced, asked for rather than waited for. A stop
        button that merely marked the row closed would take the recap, the mastery delta and the
        review schedule away from the learner who *chose* to stop and leave them only for the one
        who ran out of time, which is the wrong way round: choosing to finish is the better habit.

        Terminal already means done. A stop button is a thing people double-click, and this one
        costs a model call, so a second press returns the session that already ended rather than
        paying for a second goodbye. Under the turn slot, the ceiling and the ledger, because it
        *is* a turn: words written and paid for.

        A session still being placed or warming has nothing to end well: no map has landed, nothing
        has been taught, and a meter of an empty session is a ceremony about nothing. Those are
        abandoned instead, which is what leaving one honestly looks like.
        """
        run_id = uuid4().hex
        bind_run_id(run_id, session_id=session_id)
        context = await self._ready(session_id, owner_id)
        if context.session.status in _TERMINAL:
            return context.session
        if context.session.status in (SessionStatus.PLACING, SessionStatus.WARMING):
            return await self._abandon(context.session, owner_id=owner_id, run_id=run_id)

        session = context.session
        model = context.known
        graph = context.graph
        assert graph is not None, "an active session has a map"
        ended = await self._take_and_save(
            context,
            lambda: close_session(
                session,
                graph,
                model,
                list(session.turns),
                DirectorMove(kind=MoveKind.CLOSE, reason=_ASKED_TO_STOP),
                clock=on_the_wall(
                    SessionClock(
                        turn=len(session.turns) + 1,
                        elapsed_s=_elapsed_s(session),
                        budget_s=self._session_budget_s,
                    ),
                    session,
                ),
                tutor=self._tutor,
                run_id=run_id,
            ),
            run_id=run_id,
            owner_id=owner_id,
            slot=self._turn_slot(session_id),
        )
        assert ended is not None, "a close always writes"
        return ended

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
            return await self._abandon(session, owner_id=owner_id, run_id=None)

    async def _abandon(
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

    async def recent(self, *, owner_id: str | None = None) -> list[SessionSummary]:
        """This learner's sessions, newest first (T2).

        The one session route that names no session, which is why it takes no ``session_id`` to
        correlate by and leaves the request's own id to do it. Summaries rather than sessions: a
        list of twenty would otherwise be twenty transcripts on the wire to draw twenty rows.
        """
        listed = await asyncio.to_thread(self._sessions.recent, owner_id=owner_id)
        logger.info("live.session.listed", count=len(listed))
        return listed

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
