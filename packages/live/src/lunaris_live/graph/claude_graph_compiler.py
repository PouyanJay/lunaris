import asyncio
import json
import time
from collections.abc import Iterable
from typing import Any

import structlog
from lunaris_runtime.resilience import build_chat_model, retry_on_rate_limit
from pydantic import ValidationError

from .assembly import assemble
from .graph_compilation_error import GraphCompilationError
from .schema import (
    ConceptGraph,
    ConceptNode,
    GraphEdit,
    MasteryCriterion,
    MasteryCriterionKind,
    NodeProvenance,
    TeachingDepth,
    TeachingSpec,
)

logger = structlog.get_logger()

_DEFAULT_MAX_CONCURRENCY = 8

#: The plan's budget for a cold compile is three minutes; this sits just past it. It is a ceiling,
#: not a target — it exists so a stalled provider call fails the request instead of holding a
#: learner on a screen that will never resolve.
_DEFAULT_DEADLINE_S = 200.0

#: An extension happens mid-conversation, so its ceiling is a pause a tutor can talk over rather
#: than a wait a learner has to sit through. Past it the tutor is better off saying it doesn't know.
_DEFAULT_EXTEND_DEADLINE_S = 15.0

#: Headroom for ~20 concepts of structured JSON. The provider default is far lower, and a
#: decomposition cut off mid-object is the one failure this compiler cannot degrade around.
_DECOMPOSE_TOKENS = 8000

_DECOMPOSE_PROMPT = """You are mapping a topic into the concepts someone has to learn in order to \
understand it, and the order they have to learn them in.

Topic: "{topic}"

Break it into 12-20 atomic concepts. A concept is one idea that can be taught in a sitting — not a \
chapter, not a whole field. For each, say which of the OTHER concepts a learner must already \
understand before this one makes sense. List only DIRECT prerequisites: if A is needed for B and B \
for C, do not also list A for C.

Respond with ONLY a JSON object, no prose:
{{"concepts": [{{"id": "kebab-case-id", "name": "Short name", "definition": "One sentence, plain \
language, no jargon the learner would not already have", "requires": ["other-id"]}}]}}"""

_EXTEND_PROMPT = """A learner partway through a course on "{topic}" has asked for something the \
course does not currently cover.

They asked: "{request}"

The course already covers these concepts:
{known}

Give ONLY the genuinely new concepts needed to answer them — usually 1 to 3, never more than 5. Do \
not restate a concept that is already listed above. Each new concept may list prerequisites drawn \
from the existing ids above or from the other new concepts.

Respond with ONLY a JSON object, no prose:
{{"concepts": [{{"id": "kebab-case-id", "name": "Short name", "definition": "One sentence, plain \
language", "requires": ["existing-or-new-id"]}}]}}"""

_SPEC_PROMPT = """You are writing the teaching notes for one concept in a course about "{topic}".

Concept: "{name}" — {definition}

Give:
- objective: what the learner should be able to do once they have it. One sentence.
- misconceptions: 2-3 wrong models people actually hold about this, each written AS THE LEARNER \
WOULD BELIEVE IT, not as a correction.
- aliases: 1-3 other names a learner might call this by, including the everyday phrasing someone \
would use before they knew the technical term. Omit if the name is already the only one.
- depth: one of "intuition_first", "formal", "applied".
- criteria: 2-3 things the learner must be able to DO to prove they understand — never "knows \
that…", always an action that can be watched. Each has a "kind" of "predict" (say what happens), \
"manipulate" (change something and explain the result — set "needsSim" true, it needs an \
interactive simulator), or "explain" (teach it back).

Respond with ONLY a JSON object, no prose:
{{"objective": "...", "misconceptions": ["..."], "aliases": ["..."], "depth": "intuition_first", \
"criteria": [{{"kind": "predict", "statement": "...", "needsSim": false}}]}}"""


class ClaudeGraphCompiler:
    """Compiles a topic into a concept graph with Claude.

    Two passes. The first decomposes the topic and states the dependencies between concepts; the
    second authors each concept's teaching notes, in parallel. That is one call plus one per
    concept — deliberately not Studio's pairwise judging, which is O(n²) in model calls and would
    blow the three-minute budget many times over on a graph this size. The structure the model
    proposes is still only a proposal: ``assemble`` owns acyclicity and ordering either way, so what
    is traded away is judgment quality per edge, not correctness.

    Defensive by design, because decomposition is inference and will come back malformed. A concept
    missing its definition is dropped rather than half-taught; a spec that fails to parse leaves its
    concept standing without one. The single failure that is *not* survivable is an unparseable
    decomposition — with no concepts there is no map, and returning an empty graph would hand a
    learner a failure dressed as a finished product.
    """

    def __init__(
        self,
        model_name: str,
        *,
        client: object | None = None,
        max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
        deadline_s: float = _DEFAULT_DEADLINE_S,
        extend_deadline_s: float = _DEFAULT_EXTEND_DEADLINE_S,
    ) -> None:
        self._model_name = model_name
        # Injected in tests; production leaves it None so the client is built on first use and
        # constructing the compiler needs no API key.
        self._client = client
        self._max_concurrency = max(1, max_concurrency)
        self._deadline_s = deadline_s
        self._extend_deadline_s = extend_deadline_s

    async def compile(self, topic: str, *, graph_id: str, run_id: str) -> ConceptGraph:
        clock = time.monotonic()
        # A request that hangs is worse than one that fails: the learner waits with no way to know
        # it is never coming, and the abandoned work keeps spending tokens behind them. The timeout
        # cancels the whole tree — the in-flight authoring calls included.
        try:
            async with asyncio.timeout(self._deadline_s):
                concepts = await self._decompose(topic, run_id=run_id)
                decomposed_at = time.monotonic()
                nodes = await self._author_all(concepts, topic=topic, run_id=run_id)
                authored_at = time.monotonic()
        except TimeoutError:
            # Without this the run goes silent exactly when someone needs to read it:
            # compile_started and then nothing, with no way to tell a stalled decomposition from
            # stalled authoring — the whole reason the phases are timed separately.
            logger.warning(
                "live.graph.compile_timed_out",
                run_id=run_id,
                graph_id=graph_id,
                deadline_s=self._deadline_s,
                elapsed_ms=round((time.monotonic() - clock) * 1000),
            )
            raise

        graph = assemble(ConceptGraph(graph_id=graph_id, topic=topic, nodes=nodes))

        logger.info(
            "live.graph.compiled",
            run_id=run_id,
            graph_id=graph_id,
            compiler="claude",
            node_count=len(graph.nodes),
            unspecified=sum(1 for node in graph.nodes if node.teaching_spec is None),
            # Split by phase, because they fail differently: decomposition is one serial call whose
            # cost scales with the model, authoring is N concurrent calls whose cost scales with the
            # graph. Only measuring the total tells you a compile was slow, never which to fix.
            decompose_ms=round((decomposed_at - clock) * 1000),
            authoring_ms=round((authored_at - decomposed_at) * 1000),
        )
        return graph

    async def extend(
        self, graph: ConceptGraph, *, request: str, anchors: list[str], run_id: str
    ) -> ConceptGraph:
        """Grow the map onto one branch, for something the learner asked for mid-session.

        **Append-only with respect to what is already there.** Only new concepts are added, and
        only new concepts may declare prerequisites; an existing concept passes through untouched
        even if the model restates it. A learner is partway through this map, and a question asked
        in passing must never re-sequence the course underneath them. It also makes the result safe
        by construction: nothing existing can point at a new concept, so no loop can form through
        the settled graph, and the repair can never spend an established edge.
        """
        clock = time.monotonic()
        async with asyncio.timeout(self._extend_deadline_s):
            proposed = await self._propose_branch(graph, request=request, run_id=run_id)
            added = await self._author_all(proposed, topic=graph.topic, run_id=run_id)

        added = [node.model_copy(update={"provenance": NodeProvenance.EXTENDED}) for node in added]
        version = graph.version + 1
        edit = GraphEdit(
            version=version,
            request=request[:500],
            added=[node.id for node in added],
            anchors=[anchor for anchor in anchors if anchor in {n.id for n in graph.nodes}],
        )
        extended = assemble(
            graph.model_copy(
                update={
                    "nodes": [*graph.nodes, *added],
                    "version": version,
                    "edits": [*graph.edits, edit],
                }
            )
        )

        logger.info(
            "live.graph.extended",
            run_id=run_id,
            graph_id=graph.graph_id,
            version=version,
            added=edit.added,
            elapsed_ms=round((time.monotonic() - clock) * 1000),
        )
        return extended

    async def _propose_branch(
        self, graph: ConceptGraph, *, request: str, run_id: str
    ) -> list[dict[str, Any]]:
        """The genuinely new concepts a request needs, scoped to what the map already covers."""
        known = {node.id for node in graph.nodes}
        response = await self._ask(
            _EXTEND_PROMPT.format(
                topic=graph.topic,
                request=request,
                known="\n".join(f"- {node.id}: {node.name}" for node in graph.nodes),
            )
        )
        payload = _parse_json_object(response)
        raw = payload.get("concepts") if payload else None
        raw = raw if isinstance(raw, list) else []
        # Anything already on the map is dropped rather than merged: honouring a restatement is how
        # an extension would come to rewrite the settled graph.
        fresh = [c for c in _distinct(c for c in raw if _is_usable(c)) if c["id"] not in known]

        if not fresh:
            logger.warning("live.graph.extend_found_nothing", run_id=run_id, request=request[:200])
            raise GraphCompilationError(f"nothing new to add for {request!r}")
        return fresh

    async def _decompose(self, topic: str, *, run_id: str) -> list[dict[str, Any]]:
        response = await self._ask(
            _DECOMPOSE_PROMPT.format(topic=topic), max_tokens=_DECOMPOSE_TOKENS
        )
        payload = _parse_json_object(response)
        raw = payload.get("concepts") if payload else None
        raw = raw if isinstance(raw, list) else []
        concepts = _distinct(concept for concept in raw if _is_usable(concept))

        if not concepts:
            logger.error("live.graph.decompose_failed", run_id=run_id, topic=topic)
            raise GraphCompilationError(f"could not decompose {topic!r} into concepts")

        if len(raw) != len(concepts):
            # Silently teaching a half-formed concept — or the same concept twice under one id —
            # is worse than teaching one fewer.
            logger.warning(
                "live.graph.concepts_dropped", run_id=run_id, count=len(raw) - len(concepts)
            )
        return concepts

    async def _author_all(
        self, concepts: list[dict[str, Any]], *, topic: str, run_id: str
    ) -> list[ConceptNode]:
        """Author every concept's teaching notes concurrently, capped so a large graph doesn't
        burst past the provider's rate limit."""
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def author(concept: dict[str, Any]) -> ConceptNode | None:
            async with semaphore:
                return await self._author(concept, topic=topic, run_id=run_id)

        authored = await asyncio.gather(*(author(concept) for concept in concepts))
        return [node for node in authored if node is not None]

    async def _author(
        self, concept: dict[str, Any], *, topic: str, run_id: str
    ) -> ConceptNode | None:
        """One concept's node, or ``None`` if it could not be built at all.

        Everything here is defensive on purpose. Authoring is one call per concept out of a dozen or
        more, so a transient provider error on any single one is close to expected — and losing the
        whole map to it would cost the learner far more than losing one concept's teaching notes.
        """
        try:
            known = _identity_of(concept)
        except (ValidationError, ValueError, KeyError):
            logger.warning("live.graph.concept_unusable", run_id=run_id, concept=concept.get("id"))
            return None

        try:
            response = await self._ask(
                _SPEC_PROMPT.format(topic=topic, name=known.name, definition=known.definition)
            )
        except Exception:
            logger.warning(
                "live.graph.spec_call_failed", run_id=run_id, concept=known.id, exc_info=True
            )
            return known

        payload = _parse_json_object(response)
        if payload is None:
            logger.warning("live.graph.spec_unparseable", run_id=run_id, concept=known.id)
            return known

        return known.model_copy(
            update={
                # Aliases live on the node rather than the spec: they are how a question gets
                # resolved to this concept at all, which has to work even when authoring the rest
                # of the notes failed.
                "aliases": _parse_aliases(payload.get("aliases")),
                "teaching_spec": _parse_teaching_spec(payload, run_id=run_id, concept=known.id),
                "mastery_criteria": _parse_criteria(
                    payload.get("criteria"), run_id=run_id, concept=known.id
                ),
            }
        )

    async def _ask(self, prompt: str, *, max_tokens: int | None = None) -> str:
        if self._client is None:
            # Sized so a full decomposition is never cut off mid-object: the provider default is
            # around a thousand tokens, which a 20-concept response would overrun — and a truncated
            # decomposition is the one failure this compiler cannot degrade around.
            self._client = build_chat_model(self._model_name, max_tokens=max_tokens)
        message = await retry_on_rate_limit(lambda: self._client.ainvoke(prompt))  # type: ignore[attr-defined]
        content = message.content
        return content if isinstance(content, str) else str(content)


def _is_usable(concept: object) -> bool:
    """A concept the session could actually teach: it has an id, a name and a real definition."""
    return isinstance(concept, dict) and all(
        isinstance(concept.get(field), str) and concept[field].strip()
        for field in ("id", "name", "definition")
    )


def _distinct(concepts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The concepts under distinct ids, first occurrence winning.

    Two concepts sharing an id is a plausible decomposition slip ("gradient" and "gradient descent"
    slugging alike) and a quietly destructive one: ordering is derived over a *set* of ids, so the
    duplicate would vanish from the order while still sitting in the node list — a concept present
    on the map that the session can never reach.
    """
    seen: set[str] = set()
    distinct: list[dict[str, Any]] = []
    for concept in concepts:
        if concept["id"] not in seen:
            seen.add(concept["id"])
            distinct.append(concept)
    return distinct


def _identity_of(concept: dict[str, Any]) -> ConceptNode:
    """The node a concept describes, before any teaching notes are attached.

    Fields are clamped to the contract's own limits rather than trusted: a model that runs long
    would otherwise fail validation deep inside a gathered task, and one over-enthusiastic
    definition would take the whole compile with it.
    """
    return ConceptNode(
        id=str(concept["id"])[:100],
        name=str(concept["name"])[:200],
        definition=str(concept["definition"])[:2000],
        requires=[str(r) for r in concept.get("requires", []) if isinstance(r, str)],
        provenance=NodeProvenance.COMPILED,
    )


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """The JSON object in a model response, or ``None``.

    Models wrap JSON in prose and fences however the mood takes them, and a re-ask costs a call and
    seconds we do not have. So this normalises deterministically rather than repairing by prompt.

    It decodes forward from the first brace rather than slicing to the last one: trailing prose can
    easily contain a stray brace, and a fence marker can appear *inside* a string value the model
    wrote. Reading one well-formed object and ignoring whatever follows is both more forgiving and
    incapable of mangling the content it accepts.
    """
    start = text.find("{")
    if start == -1:
        return None
    try:
        parsed, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_aliases(raw: object) -> list[str]:
    """Other names a learner might use for a concept, deduplicated and bounded."""
    if not isinstance(raw, list):
        return []
    aliases: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip() and item[:100] not in aliases:
            aliases.append(item[:100])
    return aliases[:5]


def _parse_teaching_spec(
    payload: dict[str, Any], *, run_id: str, concept: str
) -> TeachingSpec | None:
    objective = payload.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        return None

    misconceptions = payload.get("misconceptions")
    depth = payload.get("depth")
    if depth is not None and depth not in set(TeachingDepth):
        # A model that systematically mis-names the depth would otherwise be invisible: every
        # concept would quietly read as intuition-first and the graph would look fine.
        logger.warning(
            "live.graph.depth_unrecognised", run_id=run_id, concept=concept, depth=str(depth)[:40]
        )

    return TeachingSpec(
        objective=objective[:500],
        misconceptions=[m[:500] for m in misconceptions or [] if isinstance(m, str) and m.strip()]
        if isinstance(misconceptions, list)
        else [],
        depth=TeachingDepth(depth)
        if depth in set(TeachingDepth)
        else TeachingDepth.INTUITION_FIRST,
    )


def _parse_criteria(raw: object, *, run_id: str, concept: str) -> list[MasteryCriterion]:
    """The criteria that name a kind the runtime can actually stage.

    An unrecognised kind is dropped rather than coerced: the director keys its next move off the
    kind, so guessing one would send a learner to the wrong kind of check entirely.
    """
    if not isinstance(raw, list):
        return []

    criteria: list[MasteryCriterion] = []
    dropped = 0
    for item in raw:
        kind = item.get("kind") if isinstance(item, dict) else None
        statement = item.get("statement") if isinstance(item, dict) else None
        if kind not in set(MasteryCriterionKind) or not isinstance(statement, str):
            dropped += 1
            continue
        if not statement.strip():
            dropped += 1
            continue
        criteria.append(
            MasteryCriterion(
                kind=MasteryCriterionKind(kind),
                statement=statement[:500],
                needs_sim=bool(item.get("needsSim") or item.get("needs_sim")),
            )
        )

    if dropped:
        logger.warning("live.graph.criteria_dropped", run_id=run_id, concept=concept, count=dropped)
    return criteria
