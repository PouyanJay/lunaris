"""Phase 1's exit gate: ten diverse topics, compiled for real (T9).

Excluded from the default run (marked ``eval``). Run it with a real key:

    uv run --env-file .env pytest -m eval packages/live -q -s

Every other test of this compiler feeds it a stub or a fixture, which proves the wiring and proves
nothing about the maps. This is the only place the real model is asked to decompose a real subject,
and it is where the three success criteria are checked against what it actually produced: the map is
sound and teachable, the compile fits the three-minute budget, and C1 and C2 hold on real output
rather than on a stub that was written to satisfy them.

**It does not decide whether the curriculum is right.** No machine can tell whether *supply* really
belongs before *equilibrium*. So every run writes each map out as a digest under
``.eval/live-graph/`` for a domain-literate reviewer to read — that review, not this file, is the
gate the plan names.

Topics run one at a time on purpose. Each compile is already fifteen-odd concurrent authoring calls,
and the provider's limit is per minute across the account, so two topics at once buys nothing and
risks turning a curriculum failure into a rate-limit failure.
"""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from eval_topics import TOPICS, EvalTopic
from graph_quality import complaints_about, digest
from lunaris_live.graph import (
    ClaudeGraphCompiler,
    ConceptGraph,
    NodeProvenance,
    prerequisites_of,
    resolve_request,
)

pytestmark = pytest.mark.eval

_HAS_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))
_MODEL = os.getenv("LUNARIS_MODEL_STRONG", "claude-opus-4-8")

#: Success criterion 2, and the product promise the plan states in its first sentence.
_COLD_COMPILE_BUDGET_S = 180.0
#: C1's promise: a pause a tutor can talk over, not a wait a learner sits through.
_EXTENSION_BUDGET_S = 15.0

#: How many of the ten learner paraphrases C2 has to resolve. Deliberately a fraction rather than
#: all ten: ``resolve_request`` is lexical by design, and it requires a question to name the *whole*
#: of a concept — so a map that calls something "The Gracchi and Reform Attempts" is unreachable by
#: any phrasing a person would actually use. The measured value when this landed was 8/10, with the
#: two misses of exactly that shape. Gated below the measurement so the number is a floor and not a
#: transcription of one run; the compiler is nondeterministic and names its concepts differently
#: every time, which is also why this cannot be a per-topic assertion.
_MIN_RECALL = 7

#: Where the maps land for review. Gitignored — these are model output, they cost money to make,
#: and they are read once by a human rather than diffed.
_DIGEST_DIR = Path(".eval/live-graph")


@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
@pytest.mark.parametrize("case", TOPICS, ids=lambda case: case.slug)
async def test_a_real_topic_compiles_into_a_map_worth_reviewing(case: EvalTopic) -> None:
    # Arrange
    compiler = ClaudeGraphCompiler(_MODEL, deadline_s=_COLD_COMPILE_BUDGET_S)
    run_id = uuid4().hex

    # Act — cold, from nothing but the topic string.
    started = time.monotonic()
    graph = await compiler.compile(case.topic, graph_id=case.slug, run_id=run_id)
    compiled_in = time.monotonic() - started

    # Assert — criterion 2, measured rather than assumed. The compiler's own deadline would raise
    # first, so this is what catches a budget quietly raised out from under the promise.
    assert compiled_in < _COLD_COMPILE_BUDGET_S, f"{case.topic} took {compiled_in:.0f}s"

    # Assert — criterion 1's floor. The reviewer's judgement is the gate; this only refuses to
    # spend their attention on a map that is already broken on its face.
    complaints = complaints_about(graph)
    _write_digest(case, graph, elapsed_s=compiled_in, complaints=complaints)
    assert not complaints, f"{case.topic}:\n  " + "\n  ".join(complaints)

    # Assert — C2's *precision*, per topic and without tolerance. A matcher that answered something
    # for every question would send the tutor off to answer one nobody asked, and would never route
    # to an extension at all. Recall is the softer half and is gated in aggregate below.
    assert resolve_request(graph, case.off_map) is None, (
        f"{case.off_map!r} was claimed to be already on a map of {case.topic}"
    )

    # Assert — what a covered concept needs first: the whole chain, in the map's own order.
    covered = resolve_request(graph, case.paraphrase)
    if covered is not None:
        needed = prerequisites_of(graph, covered.id)
        order = {node_id: index for index, node_id in enumerate(graph.topo_order)}
        assert needed == sorted(needed, key=lambda node_id: order[node_id])
        assert all(order[node_id] < order[covered.id] for node_id in needed)


@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
@pytest.mark.parametrize("case", TOPICS[:3], ids=lambda case: case.slug)
async def test_a_real_map_grows_onto_a_branch_it_did_not_cover(case: EvalTopic) -> None:
    """C1 against the real compiler, on the request C2 just proved the map does not cover.

    Three topics rather than ten: an extension is one branch of one map, so the tenth adds far less
    than the tenth cold compile does, and this is real money at opus rates. The three are the ones
    whose subjects are structurally most different (a quantitative model, a physical process, a
    formal calculus) — if a branch grafts cleanly onto those it is not shape-specific.
    """
    # Arrange
    compiler = ClaudeGraphCompiler(_MODEL, deadline_s=_COLD_COMPILE_BUDGET_S)
    run_id = uuid4().hex
    graph = await compiler.compile(case.topic, graph_id=case.slug, run_id=run_id)
    before = {node.id for node in graph.nodes}

    # Act
    started = time.monotonic()
    grown = await compiler.extend(graph, request=case.off_map, anchors=[], run_id=run_id)
    grew_in = time.monotonic() - started

    # Assert — C1's budget, and the map is bigger, versioned, and says why it differs.
    assert grew_in < _EXTENSION_BUDGET_S, f"the extension took {grew_in:.1f}s"
    added = {node.id for node in grown.nodes} - before
    assert added, f"nothing was added for {case.off_map!r}"
    assert grown.version == graph.version + 1
    assert grown.edits[-1].request == case.off_map
    assert set(grown.edits[-1].added) == added

    # Assert — append-only: a question asked in passing must not re-sequence the map underneath a
    # learner who is partway through it.
    was = {node.id: node for node in graph.nodes}
    assert all(node == was[node.id] for node in grown.nodes if node.id in was)
    assert all(
        node.provenance is NodeProvenance.EXTENDED for node in grown.nodes if node.id in added
    )

    # Assert — still a sound map, judged the same way the cold one was.
    assert grown.is_acyclic
    assert set(grown.topo_order) == {node.id for node in grown.nodes}

    _write_digest(case, grown, elapsed_s=grew_in, complaints=[], suffix="-extended")


@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
def test_the_maps_answer_most_of_the_questions_a_learner_would_ask() -> None:
    """C2's *recall*, over the whole run rather than one topic at a time.

    Read back off the digests the compiles just wrote, so this is measuring the same maps a human
    is about to review — and so it stays independent of the order pytest ran them in.

    Aggregate because recall is statistical here in a way precision is not: a lexical matcher's hit
    rate depends on how verbosely the model happened to name a concept this run, and pinning that
    per topic would make the exit gate a coin toss. What must never slip is the other direction,
    which every topic asserts individually above.
    """
    # Arrange
    graphs = {case.slug: _saved_graph(case) for case in TOPICS}
    available = {slug: graph for slug, graph in graphs.items() if graph is not None}
    if len(available) < len(TOPICS):
        pytest.skip(f"only {len(available)}/{len(TOPICS)} topics compiled; recall needs them all")

    # Act
    resolved = {
        case.slug: resolve_request(available[case.slug], case.paraphrase) for case in TOPICS
    }

    # Assert
    missed = sorted(slug for slug, node in resolved.items() if node is None)
    assert len(TOPICS) - len(missed) >= _MIN_RECALL, (
        f"C2 resolved only {len(TOPICS) - len(missed)}/{len(TOPICS)} paraphrases; missed: {missed}"
    )


def _saved_graph(case: EvalTopic) -> ConceptGraph | None:
    """The map this run wrote for ``case``, or ``None`` if its compile never got that far."""
    path = _DIGEST_DIR / f"{case.slug}.json"
    if not path.exists():
        return None
    return ConceptGraph.model_validate(json.loads(path.read_text()))


def _write_digest(
    case: EvalTopic,
    graph: ConceptGraph,
    *,
    elapsed_s: float,
    complaints: list[str],
    suffix: str = "",
) -> None:
    """Put the map somewhere a human can read it, and the raw graph beside it.

    Written before the assertion that could fail, so a map refused by the checker is still on disk
    to be looked at — the whole point of a compile that cost three minutes and real money is that
    nobody should have to re-run it to find out what was wrong with it.
    """
    _DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    body = digest(graph, elapsed_s=elapsed_s)
    if complaints:
        body += "\n## Refused by the automated floor\n\n" + "\n".join(f"- {c}" for c in complaints)
    (_DIGEST_DIR / f"{case.slug}{suffix}.md").write_text(body)
    # ``by_alias`` so the saved graph is byte-for-byte what the API serves: the point of keeping it
    # beside the digest is that it can be fed back to a surface, and a snake_case copy could not be.
    (_DIGEST_DIR / f"{case.slug}{suffix}.json").write_text(
        json.dumps(graph.model_dump(mode="json", by_alias=True), indent=2)
    )
