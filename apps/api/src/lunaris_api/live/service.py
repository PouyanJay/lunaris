import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import structlog
from lunaris_live.graph import (
    CompileProgress,
    ConceptGraph,
    ICompileProgressSink,
    IGraphCompiler,
    IGraphStore,
)
from lunaris_runtime.logging import bind_run_id

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
        extend_deadline_s: float = _DEFAULT_EXTEND_DEADLINE_S,
    ) -> None:
        self._compiler = compiler
        self._store = store
        self._extend_deadline_s = extend_deadline_s

    async def stream(
        self, topic: str, *, graph_id: str, run_id: str, owner_id: str | None = None
    ) -> AsyncIterator[tuple[str, CompileProgress | ConceptGraph]]:
        """The same compile as ``compile``, narrating itself as it goes.

        Yields ``("progress", …)`` per beat and one terminal ``("graph", …)``. A compile that fails
        raises here exactly as the await-full path does — the router owns how a failure is put on a
        stream, because by then the status code has already been sent.

        Unlike ``compile`` the graph id is passed *in*: the id has to reach the caller in a response
        header, before the body, so a stream that drops mid-compile can re-attach by re-reading the
        graph instead of paying for the whole compile again.
        """
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
        return await self._compile_and_save(
            topic, graph_id=uuid4().hex, run_id=run_id, owner_id=owner_id
        )

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

        graph = await self._compiler.compile(
            topic, graph_id=graph_id, run_id=run_id, on_progress=on_progress
        )
        # The store is synchronous (supabase-py is), so keep the event loop free while it writes.
        await asyncio.to_thread(self._store.save, graph, owner_id=owner_id)

        # Deliberately no explicit ``run_id=``: this line rides the contextvars binding above, so
        # the correlation test proves propagation actually works rather than only proving that the
        # id was threaded through function arguments by hand.
        logger.info(
            "live.graph.compile_finished",
            node_count=len(graph.nodes),
            is_acyclic=graph.is_acyclic,
        )
        return graph

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

        async with asyncio.timeout(self._extend_deadline_s):
            graph = await asyncio.to_thread(self._store.load, graph_id, owner_id=owner_id)
            extended = await self._compiler.extend(
                graph, request=request, anchors=anchors, run_id=run_id
            )
            await asyncio.to_thread(
                self._store.save, extended, owner_id=owner_id, expected_version=graph.version
            )

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
