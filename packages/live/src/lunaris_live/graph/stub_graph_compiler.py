import re

import structlog

from .assembly import assemble
from .schema import ConceptGraph, ConceptNode, NodeProvenance

logger = structlog.get_logger()

_MAX_SLUG_LENGTH = 40

#: Room for a derived name to wrap the topic ("Foundations of …") and still fit ConceptNode.name.
#: A concept name is a label, not a restatement of the request, so shortening here loses nothing.
_MAX_TOPIC_IN_NAME = 150


class StubGraphCompiler:
    """A deterministic compiler that needs no model, no key and no network.

    It produces a structurally valid three-concept graph for any topic — a prerequisite chain ending
    at the topic itself. It is not pretending to be a curriculum: it exists so the whole path (web →
    API → package → store) can be exercised offline and in CI, exactly as Studio's stub pipeline
    does. Real decomposition is T3, behind the same ``IGraphCompiler`` protocol.
    """

    async def compile(self, topic: str, *, graph_id: str, run_id: str) -> ConceptGraph:
        slug = _slugify(topic)
        # A topic may run to the request's full 200 characters, so names composed around it have to
        # be shortened or they overflow ConceptNode.name and fail validation on a valid request.
        label = _shorten(topic)
        nodes = [
            ConceptNode(
                id=f"{slug}-foundations",
                name=f"Foundations of {label}",
                definition=f"The ideas you need in place before {label} makes sense.",
            ),
            ConceptNode(
                id=f"{slug}-core",
                name=f"Core of {label}",
                definition=f"The central mechanism of {label}.",
                requires=[f"{slug}-foundations"],
            ),
            ConceptNode(
                id=slug,
                name=topic,
                definition=f"{topic}, put together.",
                requires=[f"{slug}-core"],
            ),
        ]
        graph = assemble(ConceptGraph(graph_id=graph_id, topic=topic, nodes=nodes))

        logger.info(
            "live.graph.compiled",
            run_id=run_id,
            graph_id=graph_id,
            compiler="stub",
            node_count=len(graph.nodes),
        )
        return graph

    async def extend(
        self, graph: ConceptGraph, *, request: str, anchors: list[str], run_id: str
    ) -> ConceptGraph:
        """Attach one concept for ``request`` onto ``anchors``, bumping the version.

        The stub's structural obligations are the ones T5 tests: the new node is marked
        ``EXTENDED``, it hangs off the named anchors, and the result is re-assembled so an extension
        can never leave the graph cyclic.
        """
        added = ConceptNode(
            id=_slugify(request),
            name=request,
            definition=f"{request}, asked for mid-session.",
            requires=[anchor for anchor in anchors if anchor in {n.id for n in graph.nodes}],
            provenance=NodeProvenance.EXTENDED,
        )
        extended = graph.model_copy(
            update={"nodes": [*graph.nodes, added], "version": graph.version + 1}
        )
        graph = assemble(extended)

        logger.info(
            "live.graph.extended",
            run_id=run_id,
            graph_id=graph.graph_id,
            compiler="stub",
            version=graph.version,
            added=added.id,
        )
        return graph


def _shorten(topic: str) -> str:
    """A topic short enough to compose a concept name around, ellipsised if it was cut."""
    topic = topic.strip()
    if len(topic) <= _MAX_TOPIC_IN_NAME:
        return topic
    return f"{topic[: _MAX_TOPIC_IN_NAME - 1].rstrip()}…"


def _slugify(text: str) -> str:
    """A stable, url-safe node id derived from prose. Deterministic — the same topic always
    compiles to the same ids, so a graph diff between two runs is readable."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return (slug or "concept")[:_MAX_SLUG_LENGTH].rstrip("-")
