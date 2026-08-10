from typing import Protocol

from ..schema import ConceptGraph
from .compile_progress_sink import ICompileProgressSink


class IGraphCompiler(Protocol):
    """Turns a topic into a concept graph.

    Injected wherever a graph is produced (DIP), so the API and the future session runtime never
    name a concrete compiler: tests run the deterministic stub, production the model-backed one.

    ``extend`` (C1) is deliberately part of the *same* protocol as ``compile``. A session will send
    the learner somewhere the map does not go, and if growing the map were a different capability
    behind a different interface, the runtime would end up choosing between them — which is how a
    tutor ends up refusing a question it should have followed. One protocol, two budgets:
    ``compile`` is cold and minutes-long, ``extend`` is warm and returns inside a spoken pause.
    """

    async def compile(
        self,
        topic: str,
        *,
        graph_id: str,
        run_id: str,
        on_progress: ICompileProgressSink | None = None,
    ) -> ConceptGraph:
        """Compile ``topic`` cold, reporting to ``on_progress`` as the work lands.

        The sink is optional and defaulted because progress is the *caller's* concern: the
        await-full POST has nobody to tell, the stream does. Only the compiler knows how many
        concepts there are, so only the compiler can count them — which is why this is a parameter
        here rather than something the API infers from the outside.
        """
        ...

    async def extend(
        self, graph: ConceptGraph, *, request: str, anchors: list[str], run_id: str
    ) -> ConceptGraph: ...
