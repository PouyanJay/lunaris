"""The simulated-learner eval: does the director actually adapt? (Phase 2a, T9)

U3's repeatable gate. An LLM plays a learner with a scripted profile, the real tutor teaches and the
real grader marks, and **the assertions are on the director's trace** — not on prose. Each profile
has to *force* a move: somebody who cannot answer must be remediated rather than marched onward,
somebody fluent must be advanced, and a specific wrong idea must be caught rather than waved past.

Prose quality is not what this measures and cannot be: it is one sample of a generative system, and
an assertion about how good an explanation reads would be a coin toss dressed as a test. What is
checkable is the *shape of the session* a learner's behaviour produces, which is exactly the thing
the policy exists to get right.

Keyed and deselected (``-m eval``), because it spends real money: one cold compile plus three
sessions of up to eight turns, each turn a tutor call, a grader call and a learner call.

    uv run --env-file .env pytest packages/live/tests/test_session_eval_live.py -m eval -q
"""

import json
import os
from dataclasses import dataclass, field

import pytest
from lunaris_live.graph import ClaudeGraphCompiler, ConceptGraph
from lunaris_live.session import (
    ClaudeGrader,
    ClaudeTutor,
    EvidenceKind,
    LearnerModel,
    MoveKind,
    Session,
    SessionClock,
    SessionStatus,
    open_session,
    take_turn,
)
from lunaris_runtime.resilience import build_chat_model, retry_on_transient

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]

_TOPIC = "How gradient descent trains a neural network"
_STRONG = "claude-opus-4-8"
_WORKER = "claude-haiku-4-5-20251001"

#: Enough turns for a policy to show its hand, bounded because every one of them costs three calls.
_MAX_TURNS = 8
_BUDGET_S = 1800.0


@dataclass
class Profile:
    """A learner to simulate, and what the director must do about them."""

    name: str
    instruction: str


_STALLS = Profile(
    name="stalls",
    instruction=(
        "You are a learner who is completely lost in this subject. You have no background in it "
        "and nothing being said is landing. Answer every question briefly, vaguely and WRONGLY — "
        "guess, say you are not sure, or describe something unrelated. Never give a correct or "
        "complete answer, even if you could. Two sentences at most, in a normal person's voice."
    ),
)

_FLUENT = Profile(
    name="fluent",
    instruction=(
        "You are a learner who already knows this subject well — you have implemented it before. "
        "Answer every question correctly, precisely and in your own words, doing exactly what was "
        "asked. Two or three sentences, no hedging, no padding."
    ),
)


def _misconceiving(graph: ConceptGraph) -> tuple[Profile, str]:
    """A learner holding the map's OWN authored misconception about the concept it opens on.

    Written from the graph rather than fixed in this file, and the first version of this test is
    why. It hard-coded a wrong idea about gradients — a concept eight turns of teaching never
    reached — so the profile answered everything else correctly and the assertion passed on an
    unrelated verdict. A misconception the session never meets proves nothing about catching them.

    Taking it from the map closes that: Phase 1 pays a model call per concept to author "the wrong
    models learners commonly hold, stated as the learner would believe them", the tutor is handed
    them, and this is the learner who actually holds one. If the loop cannot catch the misconception
    its own compiler wrote down for the concept it is teaching right now, it cannot catch any.
    """
    opening = next(node for node in graph.nodes if node.id == graph.topo_order[0])
    spec = opening.teaching_spec
    assert spec and spec.misconceptions, "the map authored no misconception to hold"
    wrong = spec.misconceptions[0]
    return (
        Profile(
            name="misconceives",
            instruction=(
                "You are a learner who is confident, articulate and holds one specific wrong idea: "
                f'you believe "{wrong}" Answer every question in that belief — fluent, sure of '
                "yourself, and wrong in exactly that way. Do not hedge and do not mention that you "
                "might be wrong. Only abandon the belief if the tutor names it directly and shows "
                "you why it is wrong. Two or three sentences."
            ),
        ),
        opening.id,
    )


@dataclass
class Trace:
    """What one simulated session did, in the terms the policy is judged on."""

    session: Session
    model: LearnerModel
    moves: list[tuple[MoveKind, str | None]] = field(default_factory=list)
    grades: list[EvidenceKind] = field(default_factory=list)

    @property
    def introduced(self) -> list[str]:
        return [node for kind, node in self.moves if kind is MoveKind.INTRODUCE and node]

    def kinds(self) -> set[MoveKind]:
        return {kind for kind, _ in self.moves}


class SimulatedLearner:
    """Answers as the profile would, given what the tutor just said.

    On the worker tier: playing a scripted role is not the quality surface, and the money in this
    eval belongs to the tutor and the grader — the two components actually under test.
    """

    def __init__(self, profile: Profile) -> None:
        self._profile = profile
        self._client = build_chat_model(_WORKER)

    async def answer(self, tutor: str, criterion: str | None) -> str:
        prompt = (
            f"{self._profile.instruction}\n\n"
            f'Your tutor just said:\n"{tutor}"\n\n'
            + (f'They asked you to: "{criterion}"\n\n' if criterion else "")
            + "Reply as yourself. Write ONLY your reply — no preamble, no quotation marks."
        )
        message = await retry_on_transient(
            lambda: self._client.ainvoke(prompt), max_attempts=3, max_delay_s=4.0
        )
        content = message.content
        said = (content if isinstance(content, str) else str(content)).strip()
        # A learner who says nothing is not a learner; the loop would refuse it and the eval would
        # be measuring the simulator rather than the policy.
        return said or "I'm not sure."


@pytest.fixture(scope="module")
async def compiled_map() -> ConceptGraph:
    """One real compile, shared by every profile.

    Real rather than hand-built because success criterion 1 is about a session on a *compiled* map:
    the teaching notes, the criteria and the ordering all come from Phase 1, and a hand-written
    graph would quietly test the policy against notes written to suit it.
    """
    return await ClaudeGraphCompiler(_STRONG).compile(_TOPIC, graph_id="eval-map", run_id="eval")


async def _run(graph: ConceptGraph, profile: Profile) -> Trace:
    """One whole session, played by ``profile`` against the real tutor and grader."""
    tutor, grader = ClaudeTutor(_STRONG), ClaudeGrader(_WORKER)
    learner = SimulatedLearner(profile)

    session = await open_session(
        graph,
        LearnerModel(graph_id=graph.graph_id),
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
        session_id=f"eval-{profile.name}",
        run_id=f"eval-{profile.name}-1",
        tutor=tutor,
    )
    trace = Trace(session=session, model=LearnerModel(graph_id=graph.graph_id))
    trace.moves.append((session.turns[0].move.kind, session.turns[0].move.node_id))

    for turn in range(2, _MAX_TURNS + 1):
        head = session.turns[-1]
        said = await learner.answer(
            head.tutor, head.criterion.statement if head.criterion else None
        )
        outcome = await take_turn(
            session,
            graph,
            trace.model,
            answer=said,
            answering_seq=head.seq,
            grader=grader,
            tutor=tutor,
            run_id=f"eval-{profile.name}-{turn}",
            elapsed_s=float(turn) * 60.0,
            budget_s=_BUDGET_S,
        )
        session, trace.model = outcome.session, outcome.model
        # The turn just answered, which is the one before the head. The head's own criterion is
        # graded on the *next* pass — so a session that runs to ``_MAX_TURNS`` leaves its last
        # question ungraded, which is a turn's worth of sample rather than a missing assertion.
        graded = session.turns[-2].grade if len(session.turns) > 1 else None
        if graded is not None:
            trace.grades.append(graded.kind)
        latest = session.turns[-1]
        trace.moves.append((latest.move.kind, latest.move.node_id))
        if session.status is SessionStatus.CLOSED:
            break

    trace.session = session
    _write_digest(profile, trace)
    return trace


def _write_digest(profile: Profile, trace: Trace) -> None:
    """Leave the transcript on disk for a human to read.

    The assertions below are the automatic gate; a session is also a thing somebody has to *read*
    before believing it teaches. Phase 1 learned this the hard way — its ten map digests were
    written and then shipped past without the domain-literate read that was the actual exit
    criterion.
    """
    out = os.path.join(os.getcwd(), ".eval", "live-session")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, f"{profile.name}.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "profile": profile.name,
                "status": trace.session.status.value,
                "turns": [
                    {
                        "seq": turn.seq,
                        "move": turn.move.kind.value,
                        "node": turn.move.node_id,
                        "why": turn.move.reason,
                        "tutor": turn.tutor,
                        "asked": turn.criterion.statement if turn.criterion else None,
                        "answer": turn.answer,
                        "grade": turn.grade.kind.value if turn.grade else None,
                        "because": turn.grade.reason if turn.grade else None,
                    }
                    for turn in trace.session.turns
                ],
            },
            handle,
            indent=2,
        )


def _assert_auditable(trace: Trace) -> None:
    """Plan §7: every move carries the reasoning that produced it.

    Asserted inside each profile rather than as a fourth session, because a session costs three
    model calls a turn and a test whose only job is to re-read a trace should not buy one of its
    own.
    """
    for turn in trace.session.turns:
        assert turn.move.reason.strip(), f"turn {turn.seq} made a choice it cannot explain"
        assert turn.tutor.strip(), f"turn {turn.seq} showed the learner nothing"
        assert turn.run_id, f"turn {turn.seq} cannot be found in the logs"


# ── the three profiles ─────────────────────────────────────────────────────────────────────────


async def test_a_learner_who_cannot_answer_is_remediated_not_marched_onward(
    compiled_map: ConceptGraph,
) -> None:
    """The single worst thing this policy could do is leave somebody stranded on the concept they
    have just failed twice, and go and teach them something else."""
    # Act
    trace = await _run(compiled_map, _STALLS)

    # Assert — the director came back to them rather than moving on.
    assert MoveKind.REMEDIATE in trace.kinds(), f"never remediated; moves were {trace.moves}"
    assert len(set(trace.introduced)) <= 2, (
        f"a learner who answered nothing correctly was walked through "
        f"{len(set(trace.introduced))} concepts: {trace.introduced}"
    )
    assert EvidenceKind.MET not in trace.grades, (
        f"the grader passed a deliberately wrong answer: {trace.grades}"
    )
    _assert_auditable(trace)


async def test_a_learner_who_knows_it_is_advanced(compiled_map: ConceptGraph) -> None:
    """The other direction, and the one a policy fails quietly: a session that cannot recognise
    somebody already fluent wastes the whole sitting re-teaching them."""
    # Act
    trace = await _run(compiled_map, _FLUENT)

    # Assert — real progress across the map, and no remediation of somebody who is not stuck.
    assert len(set(trace.introduced)) >= 2, (
        f"a fluent learner never got past one concept: {trace.moves}"
    )
    assert EvidenceKind.MET in trace.grades, f"nothing they said was marked met: {trace.grades}"
    assert MoveKind.REMEDIATE not in trace.kinds(), (
        f"a learner answering correctly was remediated: {trace.moves}"
    )
    _assert_auditable(trace)


async def test_a_specific_wrong_idea_is_caught_rather_than_waved_past(
    compiled_map: ConceptGraph,
) -> None:
    """The case the whole design is for: a learner who is *fluent* and wrong.

    They sound like somebody who knows it, which is exactly what a grader marking on confidence
    would pass — and the belief the director gates on would then record mastery of something the
    learner has backwards, and open the concepts that build on it.

    The wrong idea is the map's own, about the concept the session opens on, so it is met in the
    first turns rather than somewhere the session may never reach.
    """
    # Arrange
    profile, held_about = _misconceiving(compiled_map)

    # Act
    trace = await _run(compiled_map, profile)

    # Assert — scoped to the concept the wrong idea is ABOUT. A flat verdict list across the whole
    # session would pass on any unrelated "partial" somewhere later, and "the opening concept was
    # taught at some point" is true of every session before the learner has said a word.
    graded = [
        (turn.seq, turn.grade.kind)
        for turn in trace.session.turns
        if turn.move.node_id == held_about and turn.grade is not None
    ]
    assert graded, f"{held_about} was never graded at all: {trace.moves}"

    # The first answer is the misconception spoken aloud, fluently. Marking it correct is the exact
    # failure this profile exists to catch: a grader marking on confidence.
    assert graded[0][1] is not EvidenceKind.MET, (
        f"a confident wrong answer about {held_about} was marked correct: {trace.session.turns[0]}"
    )

    # And nothing was built on it while it was still wrong. A later MET is not a failure — it is the
    # loop working, the learner giving the idea up — but it has to come BEFORE the session moves on.
    met_at = next((seq for seq, kind in graded if kind is EvidenceKind.MET), None)
    moved_on_at = next(
        (
            turn.seq
            for turn in trace.session.turns
            if turn.move.node_id is not None and turn.move.node_id != held_about
        ),
        None,
    )
    assert moved_on_at is None or (met_at is not None and met_at < moved_on_at), (
        f"the session moved off {held_about} at turn {moved_on_at} while the learner still had it "
        f"backwards: {trace.moves}"
    )
    _assert_auditable(trace)
