import asyncio
from uuid import uuid4

import structlog
from lunaris_live.graph import ConceptGraph, IGraphCompiler, IGraphStore
from lunaris_runtime.logging import bind_run_id

logger = structlog.get_logger()


class LiveGraphService:
    """Compiles a topic into a concept graph and persists it.

    The composition root injects the compiler and the store (DIP), so this holds orchestration only:
    mint the ids, bind the correlation id, compile, persist. It deliberately owns no knowledge of
    *how* a graph is decomposed — that lives behind ``IGraphCompiler``, where the stub and the
    model-backed compiler are interchangeable.
    """

    def __init__(self, compiler: IGraphCompiler, store: IGraphStore) -> None:
        self._compiler = compiler
        self._store = store

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

    async def load(self, graph_id: str, *, owner_id: str | None = None) -> ConceptGraph:
        """Re-read a compiled graph. Raises ``FileNotFoundError`` when the caller has no such graph
        — including when it belongs to somebody else, which is not-found rather than forbidden."""
        return await asyncio.to_thread(self._store.load, graph_id, owner_id=owner_id)
