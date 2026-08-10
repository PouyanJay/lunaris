import re

import structlog

from .assembly import assemble
from .protocols import ICompileProgressSink
from .report_progress import report_progress
from .schema import (
    CompilePhase,
    ConceptGraph,
    ConceptNode,
    GraphEdit,
    MasteryCriterion,
    MasteryCriterionKind,
    NodeProvenance,
    TeachingSpec,
)

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

    async def compile(
        self,
        topic: str,
        *,
        graph_id: str,
        run_id: str,
        on_progress: ICompileProgressSink | None = None,
    ) -> ConceptGraph:
        # Reported even though this compiler finishes instantly: the keyless path runs it, and a
        # surface that only ever sees progress from the keyed compiler would be a screen nobody
        # tests. The phases are real ones, just fast.
        report_progress(on_progress, CompilePhase.DECOMPOSING)
        slug = _slugify(topic)
        # A topic may run to the request's full 200 characters, so names composed around it have to
        # be shortened or they overflow ConceptNode.name and fail validation on a valid request.
        label = _shorten(topic)
        nodes = [
            ConceptNode(
                id=f"{slug}-foundations",
                name=f"Foundations of {label}",
                definition=f"The ideas you need in place before {label} makes sense.",
                teaching_spec=_spec(f"Foundations of {label}"),
                mastery_criteria=_criteria(f"Foundations of {label}"),
            ),
            ConceptNode(
                id=f"{slug}-core",
                name=f"Core of {label}",
                definition=f"The central mechanism of {label}.",
                requires=[f"{slug}-foundations"],
                teaching_spec=_spec(f"Core of {label}"),
                mastery_criteria=_criteria(f"Core of {label}"),
            ),
            ConceptNode(
                id=slug,
                name=topic,
                definition=f"{topic}, put together.",
                requires=[f"{slug}-core"],
                teaching_spec=_spec(label),
                mastery_criteria=_criteria(label),
            ),
        ]
        for done, _ in enumerate(nodes, start=1):
            report_progress(on_progress, CompilePhase.AUTHORING, done=done, total=len(nodes))
        report_progress(on_progress, CompilePhase.ASSEMBLING, done=len(nodes), total=len(nodes))
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
        """Attach one concept for ``request``, honouring the same contract the real compiler does.

        Both implementations of ``IGraphCompiler`` have to agree on what an extension *is*, or the
        offline path would prove a contract production does not hold: append-only with respect to
        the settled map, marked EXTENDED, version bumped, and recorded in the edit log.
        """
        known = {node.id for node in graph.nodes}
        # The slug comes from the request text alone, so it can land on an id the map already has —
        # a learner echoing the topic back is enough. Two nodes under one id is silently
        # destructive: ordering is derived over a set, so the duplicate collapses out of the order
        # while both remain in the node list, and the bare new one shadows the compiled concept's
        # teaching notes for anyone building an id lookup.
        added = ConceptNode(
            id=_unused(_slugify(request), known, graph.version + 1),
            name=_shorten(request),
            definition=f"{_shorten(request)}, asked for mid-session.",
            requires=[anchor for anchor in anchors if anchor in known],
            provenance=NodeProvenance.EXTENDED,
            teaching_spec=_spec(_shorten(request)),
            mastery_criteria=_criteria(_shorten(request)),
        )
        version = graph.version + 1
        edit = GraphEdit(
            version=version,
            request=request[:500],
            added=[added.id],
            anchors=[anchor for anchor in anchors if anchor in known],
        )
        extended = assemble(
            graph.model_copy(
                update={
                    "nodes": [*graph.nodes, added],
                    "version": version,
                    "edits": [*graph.edits, edit],
                }
            )
        )

        logger.info(
            "live.graph.extended",
            run_id=run_id,
            graph_id=graph.graph_id,
            compiler="stub",
            version=version,
            added=[added.id],
        )
        return extended


def _spec(name: str) -> TeachingSpec:
    """Teaching notes for a stub concept — enough that the session loop has something to run on.

    Not decoration. A node without them is teachable *in principle* and useless in practice: the
    tutor has a definition and nothing to teach around, and the grader has no criterion to stage.
    The offline path is what CI and keyless dev run, so a stub map without notes would leave the
    whole loop below the API untested.
    """
    return TeachingSpec(
        objective=f"Explain {name} in your own words and say where it applies.",
        # Named after the concept so a session wired to the wrong node is visible rather than
        # plausible — the same reason the stub's definitions mention the topic.
        misconceptions=[f"{name} is a label to memorise rather than something to understand."],
    )


def _criteria(name: str) -> list[MasteryCriterion]:
    """One do-statement per stub concept: what the learner would be asked to demonstrate."""
    return [
        MasteryCriterion(
            kind=MasteryCriterionKind.EXPLAIN,
            statement=f"Explain {name} back in your own words.",
        )
    ]


def _unused(candidate: str, known: set[str], version: int) -> str:
    """``candidate`` if the map does not already use it, else an id disambiguated by version."""
    if candidate not in known:
        return candidate
    suffixed = f"{candidate}-v{version}"[:100]
    return suffixed if suffixed not in known else f"{candidate}-{len(known)}"[:100]


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
