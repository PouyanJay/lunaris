import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractContextManager, nullcontext
from uuid import uuid4

import structlog
from lunaris_live.graph import (
    CompileProgress,
    ConceptGraph,
    ICompileProgressSink,
    IGraphCompiler,
    IGraphStore,
)
from lunaris_runtime.credentials import CredentialResolver, run_credentials
from lunaris_runtime.logging import bind_run_id
from lunaris_runtime.metering import (
    CostScope,
    drain_cost_scope,
    enter_cost_scope,
    make_cost_scope,
)
from lunaris_runtime.persistence import ICostEventStore, ISubjectCostStore, PersistenceError
from lunaris_runtime.schema import CostSubjectType

from ..local_owner_key import LOCAL_OWNER_KEY
from .graph_throttle import CompileSlot, LiveGraphBudgetExhaustedError, LiveGraphThrottle

logger = structlog.get_logger()


def _absorb_detached_compile(
    task: "asyncio.Task[ConceptGraph]", *, run_id: str, graph_id: str
) -> None:
    """Consume the result of a compile whose stream went away, logging a failure rather than
    letting it surface as a bare unretrieved-exception warning with nothing to correlate it to.

    The ids are passed explicitly and cannot ride contextvars: the compile runs in its own task,
    which snapshots the context at creation, so the binding made *inside* that task never reaches
    the callback — which runs back in the caller's context. Without them this line would be the one
    log in the system that names a failure and gives nobody a way to find the run it belongs to.
    """
    if task.cancelled():
        return
    if (error := task.exception()) is not None:
        logger.warning(
            "live.graph.detached_compile_failed",
            run_id=run_id,
            graph_id=graph_id,
            error=str(error),
        )


#: What the drain is allowed to take out of a request's budget. Persisting a handful of ledger rows
#: is fast, but it is store I/O, and C1's promise is about the wall clock a learner waits — so it is
#: reserved for rather than added on top of the deadline, and a slow store costs telemetry, not the
#: answer.
_DRAIN_RESERVE_S = 2.0

#: What reading the graph's spend is allowed to take out of the same budget. Carved out rather than
#: added on top for the same reason as the drain: a learner must not wait longer because the ledger
#: was slow, and an admission check that cannot answer in time fails open (see
#: ``_refuse_if_budget_spent``).
_BUDGET_CHECK_RESERVE_S = 1.0

#: The largest share of the whole budget any one reserve may claim. It only binds when the budget is
#: smaller than the reserves want (a test, or a future operator turning the deadline right down) —
#: and there the reserves are what give way, because they buy telemetry and the deadline is a
#: promise to a waiting learner. Without it the reserves would be *additive* at small budgets: the
#: floor below would hand the work a full second on top of three seconds of reserves, so a
#: one-second deadline could take four.
_MAX_RESERVE_SHARE = 0.25

#: C1's budget covers the whole request, not just the thinking. The compiler bounds its own model
#: calls, but a slow database would otherwise leave a learner waiting minutes on a question asked
#: mid-conversation — which is the exact experience C1 exists to prevent.
_DEFAULT_EXTEND_DEADLINE_S = 15.0


class LiveGraphService:
    """Compiles a topic into a concept graph and persists it.

    The composition root injects the compiler and the store (DIP), so this holds orchestration only:
    mint the ids, bind the correlation id, compile, persist. It deliberately owns no knowledge of
    *how* a graph is decomposed — that lives behind ``IGraphCompiler``, where the stub and the
    model-backed compiler are interchangeable.
    """

    def __init__(
        self,
        compiler: IGraphCompiler,
        store: IGraphStore,
        *,
        cost_event_store: ICostEventStore | None = None,
        subject_cost_store: ISubjectCostStore | None = None,
        credential_resolver: CredentialResolver | None = None,
        extend_deadline_s: float = _DEFAULT_EXTEND_DEADLINE_S,
        throttle: LiveGraphThrottle | None = None,
        graph_budget_usd: float = 0.0,
    ) -> None:
        self._compiler = compiler
        self._store = store
        # Both optional: metering is observability, and it is simply off when either store is
        # unwired (offline dev, the suite). A compile must never fail for want of a ledger.
        self._cost_event_store = cost_event_store
        self._subject_cost_store = subject_cost_store
        # None when BYOK is off — the compiler then reads the process environment, unchanged.
        self._credential_resolver = credential_resolver
        self._extend_deadline_s = extend_deadline_s
        # None (the default) leaves compiles and extensions unrationed — today's behaviour, and what
        # the suites that predate T8c compose. The composition root wires the process-wide one.
        self._throttle = throttle
        # Ceiling on what one map may spend across its compile and every later extension, read from
        # the ledger's rollup. 0 (the default) is uncapped; it is a runaway guard, not a ration.
        self._graph_budget_usd = graph_budget_usd

    def stream(
        self, topic: str, *, graph_id: str, run_id: str, owner_id: str | None = None
    ) -> AsyncIterator[tuple[str, CompileProgress | ConceptGraph]]:
        """The same compile as ``compile``, narrating itself as it goes.

        Yields ``("progress", …)`` per beat and one terminal ``("graph", …)``. A compile that fails
        raises there exactly as the await-full path does — the router owns how a failure is put on a
        stream, because by then the status code has already been sent.

        Unlike ``compile`` the graph id is passed *in*: the id has to reach the caller in a response
        header, before the body, so a stream that drops mid-compile can re-attach by re-reading the
        graph instead of paying for the whole compile again.

        Deliberately **not** a generator: admission and the compile task have to happen when this is
        called, not when the body is first iterated. A generator would defer both until after the
        response status had gone out, and by then a refusal could only be said as a frame — which
        the surface reads as "the compile failed" rather than "we did not start one". So a refusal
        (:class:`LiveWorkRefusedError`) raises from here, while the response is still a status.
        """
        slot = self._reserve_compile(owner_id)
        # Everything from here to the release callback is guarded: this is the one stretch where a
        # slot is held by nothing. Every other path frees it (``compile``'s finally, the callback
        # below), so a raise in here would strand it until the process restarted — and the learner
        # it stranded would be locked out of Live with no way to tell why.
        try:
            queue: asyncio.Queue[CompileProgress] = asyncio.Queue()
            # `put_nowait` on an unbounded queue never blocks and never awaits, which is exactly the
            # contract ICompileProgressSink asks of a sink.
            compiling = asyncio.create_task(
                self._compile_and_save(
                    topic,
                    graph_id=graph_id,
                    run_id=run_id,
                    owner_id=owner_id,
                    on_progress=queue.put_nowait,
                )
            )
            # The slot is freed by the compile, never by the stream. A dropped connection does not
            # stop the compile (see the detach branch below), and a compile that is still running is
            # still spending — so releasing when the stream ends would let one learner start a
            # second three-minute compile while the first is still billing them for the same map.
            if slot is not None:
                compiling.add_done_callback(lambda _: self._release_compile(slot))
        except BaseException:
            self._release_compile(slot)
            raise
        return self._beats(compiling, queue, run_id=run_id, graph_id=graph_id)

    async def _beats(
        self,
        compiling: "asyncio.Task[ConceptGraph]",
        queue: "asyncio.Queue[CompileProgress]",
        *,
        run_id: str,
        graph_id: str,
    ) -> AsyncIterator[tuple[str, CompileProgress | ConceptGraph]]:
        """The stream's body: relay each beat as it lands, then the finished map."""
        try:
            beat = asyncio.ensure_future(queue.get())
            while True:
                await asyncio.wait({beat, compiling}, return_when=asyncio.FIRST_COMPLETED)
                if beat.done():
                    yield "progress", beat.result()
                    beat = asyncio.ensure_future(queue.get())
                    continue
                # The compile finished. Drain what it reported in its last moments before handing
                # over the map, so the bar is never left short of the graph it produced.
                beat.cancel()
                while not queue.empty():
                    yield "progress", queue.get_nowait()
                yield "graph", compiling.result()
                return
        finally:
            if not compiling.done():
                # The learner navigated away or the connection dropped. The compile is deliberately
                # NOT cancelled: it is minutes of work, it is bounded by its own deadline, and it
                # persists the graph at the end — so the id already sent in the header remains
                # re-readable. Its result has to be consumed somewhere, though, or a failure past
                # this point surfaces as an unretrieved-exception warning with no context.
                logger.info("live.graph.stream_detached", run_id=run_id, graph_id=graph_id)
                compiling.add_done_callback(
                    lambda task: _absorb_detached_compile(task, run_id=run_id, graph_id=graph_id)
                )

    async def compile(
        self, topic: str, *, run_id: str, owner_id: str | None = None
    ) -> ConceptGraph:
        slot = self._reserve_compile(owner_id)
        try:
            return await self._compile_and_save(
                topic, graph_id=uuid4().hex, run_id=run_id, owner_id=owner_id
            )
        finally:
            # Released on failure too: a compile that fell over is not still occupying the runtime,
            # and leaving the slot held would lock a learner out of Live over one bad topic.
            self._release_compile(slot)

    def _reserve_compile(self, owner_id: str | None) -> CompileSlot | None:
        """Admit a cold compile for this owner, or raise the throttle's refusal. ``None`` when no
        throttle is wired — nothing to release, nothing rationed."""
        if self._throttle is None:
            return None
        return self._throttle.reserve_compile(owner_id or LOCAL_OWNER_KEY)

    def _release_compile(self, slot: CompileSlot | None) -> None:
        """Give back an in-flight compile slot (no-op when nothing was reserved)."""
        if slot is None:
            return
        # A slot can only have come from this service's throttle, so the throttle is necessarily
        # wired here; asserting says so rather than silently skipping the release.
        assert self._throttle is not None, "a compile slot is held but no throttle is wired"
        self._throttle.release_compile(slot)

    async def _compile_and_save(
        self,
        topic: str,
        *,
        graph_id: str,
        run_id: str,
        owner_id: str | None,
        on_progress: ICompileProgressSink | None = None,
    ) -> ConceptGraph:
        """The compile itself, shared by both entry points so they cannot drift.

        Correlation is bound in here rather than by the caller because the streaming path runs this
        in its own task: a context bound outside would not be the context these lines log in.
        """
        bind_run_id(run_id, graph_id=graph_id)
        logger.info("live.graph.compile_started", topic=topic, graph_id=graph_id, run_id=run_id)

        credentials = await self._resolve_credentials(owner_id)
        cost = self._make_cost_scope(run_id=run_id, graph_id=graph_id, owner_id=owner_id)
        try:
            # The credential scope has to wrap the compiler, not just be resolved before it: the
            # model client is built on first use *inside* the compile, and it reads the tenant's
            # key off this contextvar. Without it a BYOK tenant's map is built on the platform's
            # key — money spent on their behalf that they never authorized and cannot see.
            with self._credential_scope(credentials), enter_cost_scope(cost):
                graph = await self._compiler.compile(
                    topic, graph_id=graph_id, run_id=run_id, on_progress=on_progress
                )
                # The store is synchronous (supabase-py is), so keep the loop free while it writes.
                await asyncio.to_thread(self._store.save, graph, owner_id=owner_id)
        finally:
            # Drained even when the compile failed: a run that timed out after ten of its twelve
            # calls really spent that, and a ledger recording only successes would under-report
            # exactly the runs somebody needs to go and look at.
            await self._drain(cost, run_id=run_id, graph_id=graph_id)

        # Deliberately no explicit ``run_id=``: this line rides the contextvars binding above, so
        # the correlation test proves propagation actually works rather than only proving that the
        # id was threaded through function arguments by hand.
        logger.info(
            "live.graph.compile_finished",
            node_count=len(graph.nodes),
            is_acyclic=graph.is_acyclic,
        )
        return graph

    def _make_cost_scope(
        self, *, run_id: str, graph_id: str, owner_id: str | None
    ) -> CostScope | None:
        """This run's cost scope, or ``None`` when metering is off.

        Keyed ``LIVE_GRAPH`` and stated explicitly — a graph's id and a course's are minted from
        independent sequences, so filing this under the course namespace would eventually merge two
        products' spend in rows nobody may correct (D2).
        """
        return make_cost_scope(
            self._cost_event_store,
            self._subject_cost_store,
            run_id=run_id,
            subject_type=CostSubjectType.LIVE_GRAPH,
            subject_id=graph_id,
            owner_id=owner_id,
        )

    def _work_deadline(self) -> float:
        """How long an extension's *work* gets, once the ledger's two slices are taken out.

        The budget C1 states is the whole request, so the admission check and the drain are carved
        out of it rather than added around it: a learner waiting for an answer should never wait
        longer because the ledger was slow to read or to write. The three slices therefore sum to
        the configured deadline at every value of it, which is the property worth holding — a
        budget that is only honoured at the default is not a budget.
        """
        return (
            self._extend_deadline_s
            - self._reserve(_DRAIN_RESERVE_S)
            - self._reserve(_BUDGET_CHECK_RESERVE_S)
        )

    def _reserve(self, want: float) -> float:
        """A ledger slice of the request's budget: what it wants, or its share of a budget too
        small to give it (see ``_MAX_RESERVE_SHARE``)."""
        return min(want, self._extend_deadline_s * _MAX_RESERVE_SHARE)

    async def _drain(self, cost: CostScope | None, *, run_id: str, graph_id: str) -> None:
        """Persist what the run spent, bounded — metering must never hold a learner up.

        ``drain_cost_scope`` already swallows its own failures, but not its own *duration*: it is
        store I/O, and a degraded store would otherwise extend the request by however long it takes
        to give up. A drain that runs out of time costs telemetry, which is the cheaper loss.
        """
        if cost is None:
            return
        try:
            async with asyncio.timeout(self._reserve(_DRAIN_RESERVE_S)):
                await drain_cost_scope(cost, self._cost_event_store, self._subject_cost_store)
        except TimeoutError:
            logger.warning(
                "live.graph.cost_drain_timed_out",
                run_id=run_id,
                graph_id=graph_id,
                entries=len(cost.entries),
            )

    async def _refuse_if_budget_spent(self, graph_id: str, *, owner_id: str | None) -> None:
        """Refuse to grow a map that has already spent its budget (D4).

        The number is read from the ledger's rollup rather than counted here, because the ledger is
        where a graph's spend actually lives — since T8a it can answer for a graph directly, and a
        second tally kept in memory would disagree with it the moment the process restarts.

        **Fails open.** A rollup that cannot be read in time, or at all, allows the extension: this
        is a cap on money, and metering is observability. If a degraded ledger could refuse work,
        a telemetry outage would become a product outage — and the learner would be told they are
        out of budget when in truth nobody knows what they have spent.
        """
        if self._subject_cost_store is None or self._graph_budget_usd <= 0:
            return
        try:
            async with asyncio.timeout(self._reserve(_BUDGET_CHECK_RESERVE_S)):
                spent = await self._subject_cost_store.get(
                    subject_type=CostSubjectType.LIVE_GRAPH,
                    subject_id=graph_id,
                    owner_id=owner_id,
                )
        except (PersistenceError, TimeoutError):
            logger.warning("live.graph.budget_check_failed", graph_id=graph_id, exc_info=True)
            return
        if spent is not None and spent.total_amount >= self._graph_budget_usd:
            logger.info(
                "live.graph.budget_exhausted",
                graph_id=graph_id,
                spent=spent.total_amount,
                cap=self._graph_budget_usd,
            )
            raise LiveGraphBudgetExhaustedError(
                spent=spent.total_amount, cap=self._graph_budget_usd
            )

    async def _resolve_credentials(self, owner_id: str | None) -> Mapping[str, str] | None:
        """The owner's BYOK keys for this run, or ``None`` to run on the process environment.

        ``None`` for an unowned request (auth off) or with BYOK unwired — both keep today's
        behaviour, where the compiler reads ``os.environ``.
        """
        if owner_id is None or self._credential_resolver is None:
            return None
        return await self._credential_resolver(owner_id)

    @staticmethod
    def _credential_scope(
        credentials: Mapping[str, str] | None,
    ) -> AbstractContextManager[None]:
        """The run's credential context: the tenant's keys when present, else a no-op (env
        fallback). Mirrors the course build's scope so one tenant's key can never outlive its own
        request."""
        if credentials is None:
            return nullcontext()
        return run_credentials(credentials)

    async def extend(
        self,
        graph_id: str,
        *,
        request: str,
        anchors: list[str],
        run_id: str,
        owner_id: str | None = None,
    ) -> ConceptGraph:
        """Grow a stored graph onto one branch, for something asked mid-session (C1).

        Read, extend, write conditionally on the version we read — so two overlapping turns cannot
        silently discard each other's concepts. A conflict surfaces to the caller rather than being
        retried here: the right recovery is to re-read and decide again with the newer map, which is
        a judgement the session owns, not the store.
        """
        # Bound and correlated before any I/O: the graph id is known from the path, so deferring
        # either only means a hung load leaves no trace that the request ever arrived.
        bind_run_id(run_id, graph_id=graph_id)
        logger.info("live.graph.extend_started", request=request[:200], run_id=run_id)

        # Admission first, and in this order: what the map has already cost is the cap that means
        # something, and the volume counter should only count extensions that were let through.
        await self._refuse_if_budget_spent(graph_id, owner_id=owner_id)
        if self._throttle is not None:
            self._throttle.admit_extension(graph_id)

        # Metered against the same graph, so an extension accumulates on that map's total rather
        # than opening a second one: growing a map mid-session is more spend on the same subject.
        cost = self._make_cost_scope(run_id=run_id, graph_id=graph_id, owner_id=owner_id)
        try:
            # Everything the learner waits on is inside the deadline — including resolving their
            # BYOK keys, which is one vault round trip per configured provider. Work left outside
            # this scope is work the budget does not actually bound, which is the same defect T5
            # fixed here once already for the store load and save.
            async with asyncio.timeout(self._work_deadline()):
                credentials = await self._resolve_credentials(owner_id)
                with self._credential_scope(credentials), enter_cost_scope(cost):
                    graph = await asyncio.to_thread(self._store.load, graph_id, owner_id=owner_id)
                    extended = await self._compiler.extend(
                        graph, request=request, anchors=anchors, run_id=run_id
                    )
                    await asyncio.to_thread(
                        self._store.save,
                        extended,
                        owner_id=owner_id,
                        expected_version=graph.version,
                    )
        finally:
            await self._drain(cost, run_id=run_id, graph_id=graph_id)

        logger.info(
            "live.graph.extend_finished",
            version=extended.version,
            node_count=len(extended.nodes),
        )
        return extended

    async def load(self, graph_id: str, *, owner_id: str | None = None) -> ConceptGraph:
        """Re-read a compiled graph. Raises ``FileNotFoundError`` when the caller has no such graph
        — including when it belongs to somebody else, which is not-found rather than forbidden."""
        return await asyncio.to_thread(self._store.load, graph_id, owner_id=owner_id)
