import asyncio
from uuid import uuid4

import structlog
from lunaris_live.graph import ConceptGraph, IGraphCompiler, IGraphStore
from lunaris_runtime.logging import bind_run_id

logger = structlog.get_logger()

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

    async def compile(
        self, topic: str, *, run_id: str, owner_id: str | None = None
    ) -> ConceptGraph:
        graph_id = uuid4().hex
        bind_run_id(run_id, graph_id=graph_id)
        logger.info("live.graph.compile_started", topic=topic, graph_id=graph_id, run_id=run_id)

        graph = await self._compiler.compile(topic, graph_id=graph_id, run_id=run_id)
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
