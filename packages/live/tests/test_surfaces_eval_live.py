"""The generative surfaces under a real key: what a keyed session actually puts on screen, and what
it costs (Phase 2b, T10).

P2a's eval asked whether the director adapts; every assertion there is on the trace of *moves*. This
one asks about the surfaces P2b put around those moves, with the real tutor writing the words and
the material, the real grader marking, and an LLM playing the learner. What can be checked:

1. **Every turn streams.** The tutor's words leave in fragments as they are written (T2/AD4), and
   what streamed is exactly what the turn stored. Pinned per turn, against the real provider, which
   the offline suite cannot do.
2. **Every turn carries its card and its layout**, the card is the one the rules give that move
   (T3), and the layout is on the catalog with the tutor's material in it (T5); how often the
   material arrives inside its grace window is measured, because that grace was set without a
   real model on the other end.
3. **What a turn costs.** Every turn runs under a cost scope with the ledger's own price book, so
   the digest carries the USD per turn that AD49's ceiling was reasoned about rather than measured.

Prose quality is still not measured (one sample of a generative system). Two learners rather than
three: the fluent one shows advancing, the stalled one shows remediation and the quiz; six turns
each, because every turn is now four model calls (tutor, material, grader, learner).

    uv run --env-file .env pytest packages/live/tests/test_surfaces_eval_live.py -m eval -q
"""

import json
import os
from dataclasses import dataclass, field

import pytest
from lunaris_live.graph import ClaudeGraphCompiler, ConceptGraph
from lunaris_live.graph.schema import MasteryCriterionKind
from lunaris_live.session import (
    ClaudeGrader,
    ClaudeTutor,
    LearnerModel,
    MoveKind,
    Session,
    SessionClock,
    SessionStatus,
    SurfaceKind,
    open_session,
    take_turn,
)
from lunaris_runtime.metering import drain_cost_scope, enter_cost_scope, make_cost_scope
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemorySubjectCostStore
from lunaris_runtime.resilience import build_chat_model, retry_on_transient
from lunaris_runtime.schema import CostSubjectType

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]

_TOPIC = "How gradient descent trains a neural network"
_STRONG = "claude-opus-4-8"
_WORKER = "claude-haiku-4-5-20251001"
_MAX_TURNS = 6
_BUDGET_S = 1800.0

#: The rules' own mapping from move to card (T3), for the moves the move alone decides. An
#: INTRODUCE is decided by the criterion the turn staged, which the compiler authored this time, so
#: it is read off the stored turn instead (``_expected_card``).
_CARD_FOR_MOVE = {
    MoveKind.CLOSE: {SurfaceKind.MASTERY_METER},
    MoveKind.RETRIEVE: {SurfaceKind.EXPLAIN_BACK},
    MoveKind.REMEDIATE: {SurfaceKind.QUIZ_CARD, SurfaceKind.CRITERION_CARD},
}


def _expected_card(record: "TurnRecord", session: Session) -> set[SurfaceKind]:
    """The card the rules give this turn, from what the turn actually staged."""
    if MoveKind(record.move) in _CARD_FOR_MOVE:
        return _CARD_FOR_MOVE[MoveKind(record.move)]
    criterion = session.turns[record.seq - 1].criterion
    if criterion is None:
        return {SurfaceKind.CONCEPT_MAP}
    if criterion.kind is MasteryCriterionKind.EXPLAIN:
        return {SurfaceKind.EXPLAIN_BACK}
    return {SurfaceKind.CRITERION_CARD}


@dataclass
class Profile:
    name: str
    instruction: str


_STALLS = Profile(
    name="stalls",
    instruction=(
        "You are a learner who is completely lost in this subject. Answer every question briefly, "
        "vaguely and WRONGLY: guess, say you are not sure, or describe something unrelated. Never "
        "give a correct or complete answer. Two sentences at most, in a normal person's voice."
    ),
)

_FLUENT = Profile(
    name="fluent",
    instruction=(
        "You are a learner who already knows this subject well. Answer every question correctly, "
        "precisely and in your own words, doing exactly what was asked. Two or three sentences."
    ),
)


@dataclass
class TurnRecord:
    seq: int
    move: str
    node: str | None
    card: str | None
    layout: list[str]
    material: bool
    fragments: int
    streamed_matches_stored: bool
    usd: float
    grade: str | None


@dataclass
class Trace:
    session: Session
    turns: list[TurnRecord] = field(default_factory=list)


class SimulatedLearner:
    def __init__(self, profile: Profile) -> None:
        self._profile = profile
        self._client = build_chat_model(_WORKER)

    async def answer(self, tutor: str, criterion: str | None) -> str:
        prompt = (
            f"{self._profile.instruction}\n\n"
            f'Your tutor just said:\n"{tutor}"\n\n'
            + (f'They asked you to: "{criterion}"\n\n' if criterion else "")
            + "Reply as yourself. Write ONLY your reply, no preamble, no quotation marks."
        )
        message = await retry_on_transient(
            lambda: self._client.ainvoke(prompt), max_attempts=3, max_delay_s=4.0
        )
        content = message.content
        return (content if isinstance(content, str) else str(content)).strip() or "I'm not sure."


@pytest.fixture(scope="module")
async def compiled_map() -> ConceptGraph:
    return await ClaudeGraphCompiler(_STRONG).compile(_TOPIC, graph_id="eval-map", run_id="eval")


class _Ledger:
    """A per-turn cost scope over in-memory stores, so each turn's spend is a number."""

    def __init__(self, session_id: str) -> None:
        self.events, self.rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
        self._session_id = session_id

    def scope(self, run_id: str):
        return make_cost_scope(
            self.events,
            self.rollup,
            run_id=run_id,
            subject_type=CostSubjectType.LIVE_SESSION,
            subject_id=self._session_id,
            owner_id=None,
        )

    async def total(self) -> float:
        spent = await self.rollup.get(
            subject_type=CostSubjectType.LIVE_SESSION, subject_id=self._session_id, owner_id=None
        )
        return spent.total_amount if spent else 0.0


def _record(session: Session, *, fragments: list[str], usd: float) -> TurnRecord:
    """The standing turn, in the terms this eval judges: what it showed and what it cost. The
    grade recorded is the one on the turn just answered (the one before the head)."""
    head = session.turns[-1]
    answered = session.turns[-2] if len(session.turns) > 1 else None
    layout = [block.component.value for block in head.layout.blocks] if head.layout else []
    return TurnRecord(
        seq=head.seq,
        move=head.move.kind.value,
        node=head.move.node_id,
        card=head.surface.kind.value if head.surface else None,
        layout=layout,
        material=any(name in ("WorkedExample", "Hint", "Practice") for name in layout),
        fragments=len(fragments),
        streamed_matches_stored="".join(fragments).strip() == head.tutor.strip(),
        usd=usd,
        grade=answered.grade.kind.value if answered and answered.grade else None,
    )


async def _run(graph: ConceptGraph, profile: Profile) -> Trace:
    tutor, grader = ClaudeTutor(_STRONG), ClaudeGrader(_WORKER)
    learner = SimulatedLearner(profile)
    ledger = _Ledger(f"eval-{profile.name}")

    cost = ledger.scope(f"eval-{profile.name}-1")
    with enter_cost_scope(cost):
        session = (
            await open_session(
                graph,
                LearnerModel(graph_id=graph.graph_id),
                SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
                session_id=f"eval-{profile.name}",
                run_id=f"eval-{profile.name}-1",
                tutor=tutor,
            )
        ).session
    await drain_cost_scope(cost, ledger.events, ledger.rollup)
    spent_before = await ledger.total()
    trace = Trace(session=session)
    trace.turns.append(_record(session, fragments=[session.turns[0].tutor], usd=spent_before))
    model = LearnerModel(graph_id=graph.graph_id)

    for turn in range(2, _MAX_TURNS + 1):
        head = session.turns[-1]
        said = await learner.answer(
            head.tutor, head.criterion.statement if head.criterion else None
        )
        fragments: list[str] = []
        cost = ledger.scope(f"eval-{profile.name}-{turn}")
        with enter_cost_scope(cost):
            outcome = await take_turn(
                session,
                graph,
                model,
                answer=said,
                answering_seq=head.seq,
                grader=grader,
                tutor=tutor,
                run_id=f"eval-{profile.name}-{turn}",
                elapsed_s=float(turn) * 60.0,
                budget_s=_BUDGET_S,
                on_delta=fragments.append,
            )
        await drain_cost_scope(cost, ledger.events, ledger.rollup)
        spent_now = await ledger.total()
        session, model = outcome.session, outcome.model
        trace.turns.append(_record(session, fragments=fragments, usd=spent_now - spent_before))
        spent_before = spent_now
        if session.status is SessionStatus.CLOSED:
            break

    trace.session = session
    _write_digest(profile, trace, total_usd=spent_before)
    return trace


def _write_digest(profile: Profile, trace: Trace, *, total_usd: float) -> None:
    out = os.path.join(os.getcwd(), ".eval", "live-surfaces")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, f"{profile.name}.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "profile": profile.name,
                "status": trace.session.status.value,
                "total_usd": round(total_usd, 4),
                "turns": [
                    {
                        **record.__dict__,
                        "usd": round(record.usd, 4),
                        "tutor": trace.session.turns[record.seq - 1].tutor,
                        "answer": trace.session.turns[record.seq - 1].answer,
                        "surface": trace.session.turns[record.seq - 1].surface.model_dump(
                            by_alias=True, mode="json"
                        )
                        if trace.session.turns[record.seq - 1].surface
                        else None,
                    }
                    for record in trace.turns
                ],
            },
            handle,
            indent=2,
        )


def _assert_surfaces(trace: Trace) -> None:
    """What every keyed turn owes the learner, whichever profile is sitting."""
    answered = trace.turns[1:]  # the opening turn is taught whole, not streamed
    for record in answered:
        assert record.fragments > 1, f"turn {record.seq} arrived in one piece: it did not stream"
        assert record.streamed_matches_stored, f"turn {record.seq}: streamed != stored"
    for record in trace.turns:
        assert record.card is not None, f"turn {record.seq} put no card on screen"
        allowed = _expected_card(record, trace.session)
        assert SurfaceKind(record.card) in allowed, (
            f"turn {record.seq}: a {record.move} move showed {record.card}, not one of {allowed}"
        )
        if record.move != MoveKind.CLOSE.value:
            assert record.layout, f"turn {record.seq} has no layout"
            assert "Prose" in record.layout and "Surface" in record.layout, record.layout
    # A keyed turn is two model calls plus a grade (T5, AD49): a runaway would show here first.
    for record in answered:
        assert record.usd < 1.0, f"turn {record.seq} cost ${record.usd:.2f}"


async def test_a_stalled_learner_meets_the_quiz_and_every_turn_streams(
    compiled_map: ConceptGraph,
) -> None:
    trace = await _run(compiled_map, _STALLS)

    _assert_surfaces(trace)
    cards = {record.card for record in trace.turns}
    assert SurfaceKind.QUIZ_CARD.value in cards, (
        f"a learner who missed everything was never shown the misconceptions: {cards}"
    )


async def test_a_fluent_learner_advances_and_the_material_mostly_arrives(
    compiled_map: ConceptGraph,
) -> None:
    trace = await _run(compiled_map, _FLUENT)

    _assert_surfaces(trace)
    nodes = {record.node for record in trace.turns if record.node}
    assert len(nodes) >= 2, f"a fluent learner never got past one concept: {nodes}"
    # T5's material is asked for beside the words and given `_GRACE_S` after them; with the real
    # model on the other end this is how often it made it. Not a hard floor: it is the number that
    # says whether the grace is set right (it was not, at 2 s: 2/6 and 3/6; at 4 s: 6/6), and it
    # goes in the digest either way.
    with_material = sum(1 for record in trace.turns if record.material)
    assert with_material >= len(trace.turns) // 2, (
        f"the material arrived on {with_material}/{len(trace.turns)} turns"
    )
