"""Tier 1: the director picks the component, and nothing generative gets a vote (Phase 2b, T3).

Plan §8 makes this the hard rule of the tier: *"deterministic rendering is mandatory here because
these components feed the learner model — a broken assessment surface corrupts data."* So the
component on screen and every prop in it are a function of the director's move, the concept the map
authored, and what the learner is believed to know. The tutor's generative freedom is Tier 2 layout
(T5), where a mistake is cosmetic instead of corrupting.

Which makes the load-bearing test here a boring one: **the same move yields the same spec, always.**
A surface that varied — even helpfully, even rarely — would mean two learners in the same state were
assessed by different instruments, and the mastery numbers underneath them would stop being
comparable without anything ever looking broken.

The second claim is that the props are *the map's own words*: the quiz's distractors are the
misconceptions Phase 1 paid a model call per concept to author "as the learner would believe them",
not new text invented at render time.
"""

import os
import subprocess
import sys
from inspect import signature

import pytest
from lunaris_live.graph import (
    ConceptGraph,
    ConceptNode,
    MasteryCriterion,
    MasteryCriterionKind,
    TeachingSpec,
)
from lunaris_live.session import (
    DirectorMove,
    EvidenceKind,
    LearnerModel,
    MoveKind,
    SessionClock,
    SessionTurn,
    StubGrader,
    StubTutor,
    SurfaceKind,
    apply_evidence,
    open_session,
    select_surface,
    stage_criterion,
    take_turn,
)

_MISCONCEPTIONS = [
    "A gradient tells you how big the loss is.",
    "A gradient points uphill, towards the answer.",
]


def _node(
    node_id: str = "gradient",
    *,
    kind: MasteryCriterionKind = MasteryCriterionKind.PREDICT,
    misconceptions: list[str] | None = None,
    needs_sim: bool = False,
    requires: list[str] | None = None,
) -> ConceptNode:
    return ConceptNode(
        id=node_id,
        name=node_id.title(),
        definition=f"What {node_id} actually is.",
        requires=requires or [],
        teaching_spec=TeachingSpec(
            objective=f"Use {node_id}.",
            misconceptions=_MISCONCEPTIONS if misconceptions is None else misconceptions,
        ),
        mastery_criteria=[
            MasteryCriterion(
                kind=kind, statement=f"Say which way {node_id} moves.", needs_sim=needs_sim
            )
        ],
    )


def _graph(*nodes: ConceptNode) -> ConceptGraph:
    used = nodes or (_node(),)
    return ConceptGraph(
        graph_id="g1",
        topic="How neural networks learn",
        nodes=list(used),
        topo_order=[node.id for node in used],
        is_acyclic=True,
    )


def _move(kind: MoveKind = MoveKind.INTRODUCE, node_id: str | None = "gradient") -> DirectorMove:
    return DirectorMove(kind=kind, node_id=node_id, reason="Because the test says so.")


def _clock(turn: int = 3) -> SessionClock:
    return SessionClock(turn=turn, elapsed_s=60.0, budget_s=1800.0)


def _selected(
    move: DirectorMove,
    *,
    node: ConceptNode | None = None,
    graph: ConceptGraph | None = None,
    model: LearnerModel | None = None,
):
    used_node = node if node is not None else _node()
    used_graph = graph if graph is not None else _graph(used_node)
    return select_surface(
        move,
        used_node if move.kind is not MoveKind.CLOSE else None,
        graph=used_graph,
        criterion=stage_criterion(used_node) if move.kind is not MoveKind.CLOSE else None,
        model=model if model is not None else LearnerModel(graph_id="g1"),
        clock=_clock(),
    )


# ── the task's RED assertion ───────────────────────────────────────────────────────────────────


def test_the_same_move_always_yields_the_same_spec() -> None:
    """The rule the whole tier rests on.

    Nothing here is sampled, ordered by a set's iteration, or seeded from a clock. A surface that
    varied between two learners in the same state would mean they were assessed by different
    instruments — and the mastery numbers underneath them would quietly stop being comparable, with
    nothing on screen ever looking wrong.
    """
    # Arrange
    move = _move(MoveKind.REMEDIATE)

    # Act — the same inputs, built fresh each time so no object identity is shared.
    specs = [_selected(move) for _ in range(5)]

    # Assert — identical, field for field, including the order of the quiz's options.
    assert all(spec == specs[0] for spec in specs)


def test_the_spec_is_decided_without_asking_anything_generative() -> None:
    """A structural claim, not a behavioural one: ``select_surface`` is a pure function over the
    move, the map and the belief. It takes no tutor, no grader and no client, so there is no seam
    a model could be threaded through without changing this signature — which is what makes the
    determinism above a property of the design rather than of today's implementation."""
    # Arrange / Act
    parameters = set(signature(select_surface).parameters)

    # Assert
    assert parameters == {"move", "node", "graph", "criterion", "model", "clock"}


# ── one rule per situation, and the order is the policy ────────────────────────────────────────


def test_a_closing_session_shows_what_the_learner_demonstrated() -> None:
    """A close is about the session, not a concept, so the surface is too. It is also the only
    moment a meter is worth the space: mid-session it would invite the learner to optimise the
    number instead of the understanding."""
    # Arrange — two concepts with evidence behind them.
    model = LearnerModel(graph_id="g1")
    for turn in range(1, 4):
        model = apply_evidence(model, "gradient", EvidenceKind.MET, at_turn=turn)
    model = apply_evidence(model, "loss", EvidenceKind.PARTIAL, at_turn=2)

    # Act
    spec = _selected(
        _move(MoveKind.CLOSE, node_id=None),
        graph=_graph(_node(), _node("loss")),
        model=model,
    )

    # Assert — every concept the learner has evidence about, and nothing they never met, in the
    # map's own teaching order rather than the order this session happened to touch them in.
    assert spec.kind is SurfaceKind.MASTERY_METER
    assert [entry.node_id for entry in spec.entries] == ["gradient", "loss"]
    assert all(entry.concept for entry in spec.entries), "a meter of bare ids is unreadable"
    assert [entry.evidence_count for entry in spec.entries] == [3, 1]


def test_the_meter_orders_concepts_by_the_map_and_not_by_the_session() -> None:
    """Two sittings that wander differently must tell the same story about the same learner.

    Insertion order is the order the *director* happened to reach for things, which differs between
    sessions — so a meter read off the belief dictionary would rearrange itself between two runs
    that ended in exactly the same place.
    """
    # Arrange — evidence arriving in the reverse of the map's teaching order, on concepts whose
    # names sort the *other* way. Both halves are needed: with ids that happen to be alphabetical,
    # a fallback that sorted them would be indistinguishable from one that read the map, and the
    # test would pass over exactly the bug it is written for.
    model = LearnerModel(graph_id="g1")
    model = apply_evidence(model, "alpha", EvidenceKind.MET, at_turn=1)
    model = apply_evidence(model, "zeta", EvidenceKind.MET, at_turn=2)

    # Act — the map teaches zeta first.
    spec = _selected(
        _move(MoveKind.CLOSE, node_id=None),
        graph=_graph(_node("zeta"), _node("alpha")),
        model=model,
    )

    # Assert
    assert [entry.node_id for entry in spec.entries] == ["zeta", "alpha"]


def test_the_meter_shows_what_is_recalled_now_rather_than_what_was_once_shown() -> None:
    """The stored estimate is the belief at its last evidence; the meter is what they hold today.

    Showing the undecayed number would tell somebody they still have a concept they last touched
    forty minutes and six concepts ago — which is precisely the belief the director has already
    stopped acting on, so the learner and the system would be reading different meters.
    """
    # Arrange — a concept demonstrated long ago, at the very start of a long session.
    model = LearnerModel(graph_id="g1")
    for turn in range(1, 4):
        model = apply_evidence(model, "gradient", EvidenceKind.MET, at_turn=turn)
    stored = model.nodes["gradient"].estimate

    # Act — the session closes many turns later.
    spec = select_surface(
        _move(MoveKind.CLOSE, node_id=None),
        None,
        graph=_graph(_node()),
        criterion=None,
        model=model,
        clock=SessionClock(turn=40, elapsed_s=1700.0, budget_s=1800.0),
    )

    # Assert — below what was stored, and still above zero: they did demonstrate it once.
    shown = spec.entries[0].recall
    assert shown < stored, f"the meter is showing the undecayed belief ({shown} vs {stored})"
    assert shown > 0.0


def test_retrieval_asks_the_learner_to_produce_it_rather_than_recognise_it() -> None:
    """Spaced retrieval only works if the learner does the retrieving. A card offering options
    would let recognition stand in for recall, which is the one substitution that makes the whole
    move pointless."""
    # Act
    spec = _selected(_move(MoveKind.RETRIEVE))

    # Assert
    assert spec.kind is SurfaceKind.EXPLAIN_BACK
    assert "Gradient" in spec.prompt


def test_remediation_puts_the_learners_likely_wrong_model_in_front_of_them() -> None:
    """The director only remediates after two misses, so the explanation has already failed twice.
    The useful question then is not "can you say it" but "which of these do you believe" — and
    Phase 1 authored exactly that list, per concept, as the learner would believe it."""
    # Act
    spec = _selected(_move(MoveKind.REMEDIATE))

    # Assert — the map's own authored misconceptions, verbatim, plus the truth to pick out of them.
    assert spec.kind is SurfaceKind.QUIZ_CARD
    assert set(_MISCONCEPTIONS) < set(spec.options)
    assert "What gradient actually is." in spec.options


def test_a_concept_asking_to_be_explained_gets_a_place_to_explain_it() -> None:
    # Act
    spec = _selected(_move(), node=_node(kind=MasteryCriterionKind.EXPLAIN))

    # Assert
    assert spec.kind is SurfaceKind.EXPLAIN_BACK


def test_a_concept_asking_for_a_prediction_gets_the_do_statement_it_will_be_marked_on() -> None:
    """U1's mechanism, made visible: the learner answers the criterion the turn staged, and a
    separate grader scores that answer against that statement. The card shows the statement rather
    than paraphrasing it, so what they are marked on is what they were shown."""
    # Arrange
    node = _node(kind=MasteryCriterionKind.PREDICT)

    # Act
    spec = _selected(_move(), node=node)

    # Assert
    assert spec.kind is SurfaceKind.CRITERION_CARD
    assert spec.statement == node.mastery_criteria[0].statement
    assert spec.asks is MasteryCriterionKind.PREDICT


def test_a_concept_this_session_cannot_check_shows_where_it_sits_instead_of_pretending() -> None:
    """Every criterion needs a simulator (Phase 3), so nothing said next can move a belief. Staging
    a card that looks like an assessment would collect an answer that is scored against nothing —
    the surface would be lying about what the turn is for."""
    # Arrange
    node = _node("dynamics", needs_sim=True, requires=["gradient"])
    graph = _graph(_node(), node)

    # Act
    spec = _selected(_move(node_id="dynamics"), node=node, graph=graph)

    # Assert — where it sits, read off the map's own prerequisite chain (C2).
    assert spec.kind is SurfaceKind.CONCEPT_MAP
    assert spec.focus_node_id == "dynamics"
    assert spec.prerequisites == ["Gradient"], "the chain is named, not id-numbered"


# ── the quiz is built from the map, and gives nothing away ─────────────────────────────────────


def test_the_true_option_is_not_always_in_the_same_place() -> None:
    """Deterministic is not the same as predictable-by-position. If the definition always came
    first, a learner could pass every remediation in the product without reading one."""
    # Arrange — several concepts, each with the same shape of options.
    nodes = [_node(f"concept{index}") for index in range(8)]

    # Act
    positions = {
        _selected(_move(MoveKind.REMEDIATE, node_id=node.id), node=node).options.index(
            node.definition
        )
        for node in nodes
    }

    # Assert
    assert len(positions) > 1, f"the truth sat in position {positions} every time"


def test_a_concept_with_no_authored_misconceptions_is_not_quizzed_on_nothing() -> None:
    """``teaching_spec`` is optional by contract and its misconceptions may be empty — one failed
    authoring call in Phase 1 leaves a concept teachable but with nothing to quiz against. A quiz
    of one option is not a question."""
    # Act
    spec = _selected(_move(MoveKind.REMEDIATE), node=_node(misconceptions=[]))

    # Assert — the exact surface it falls through to. "Not a quiz" would also be satisfied by a
    # regression that discarded the criterion and showed a concept map, which is a different bug
    # wearing the same green tick.
    assert spec.kind is SurfaceKind.CRITERION_CARD


# ── the spec rides the turn, so a reload renders the same card ─────────────────────────────────


async def test_the_turn_records_the_surface_it_put_up() -> None:
    """R4: the spec rides the session JSON, so it needs no table and no second source of truth.

    A turn that recorded only its prose would leave a reloaded tab unable to re-render the card the
    learner was halfway through answering — and re-deriving it on read would be a second
    implementation of the rule set, free to disagree with the one that ran.
    """
    # Arrange
    graph = _graph(_node(), _node("loss"))
    opened = await open_session(
        graph,
        LearnerModel(graph_id="g1"),
        _clock(turn=1),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )

    # Act
    outcome = await take_turn(
        opened,
        graph,
        LearnerModel(graph_id="g1"),
        answer="Something worth grading.",
        answering_seq=1,
        grader=StubGrader(),
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=1.0,
        budget_s=1800.0,
    )

    # Assert — both the opening turn and the one the loop just took carry their own surface.
    assert opened.turns[0].surface is not None
    assert outcome.session.turns[-1].surface is not None
    assert outcome.session.turns[0].surface == opened.turns[0].surface, (
        "answering a turn must not rewrite the card it was answered on"
    )


async def test_the_recorded_surface_is_the_one_the_rules_would_pick_again() -> None:
    """The turn is a *record* of the decision, not a cache of a guess. If the two could differ, the
    audit trail plan §7 asks for would be describing a session that did not happen."""
    # Arrange
    graph = _graph(_node())

    # Act
    opened = await open_session(
        graph,
        LearnerModel(graph_id="g1"),
        _clock(turn=1),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )

    # Assert
    turn = opened.turns[0]
    assert turn.surface == select_surface(
        turn.move,
        graph.nodes[0],
        graph=graph,
        criterion=turn.criterion,
        model=LearnerModel(graph_id="g1"),
        clock=_clock(turn=1),
    )


def test_a_turn_stored_before_this_task_still_parses() -> None:
    """Every session row written by P2a has no ``surface`` field. Making it required would make the
    whole of Live's stored history unreadable — the failure mode ``SessionFormatError`` exists to
    report, caused by us rather than by a corrupt row."""
    # Arrange — a turn exactly as P2a wrote one.
    stored = {
        "seq": 1,
        "move": {"kind": "introduce", "nodeId": "gradient", "reason": "Because."},
        "tutor": "Let's start with Gradient.",
        "runId": "r1",
    }

    # Act
    turn = SessionTurn.model_validate(stored)

    # Assert
    assert turn.surface is None


# ── the paths review found, which the rules had not been asked about ───────────────────────────


def test_a_remediation_with_nothing_to_quiz_on_does_not_ask_them_to_say_it_again() -> None:
    """The fall-through from rule 3, and the reason it skips rule 5.

    A concept whose authoring call failed has no misconceptions, so a remediation has nothing to
    put in front of the learner — and if its criterion happens to be EXPLAIN, the obvious
    fall-through hands them "say it back in your own words". That is exactly the instrument that has
    already failed twice, which is what the director remediating at all means. They get the
    do-statement instead: a different ask, and the one they are actually marked on.
    """
    # Arrange — the combination: stuck, nothing authored, and an explain-shaped criterion.
    node = _node(kind=MasteryCriterionKind.EXPLAIN, misconceptions=[])

    # Act
    spec = _selected(_move(MoveKind.REMEDIATE), node=node)

    # Assert
    assert spec.kind is SurfaceKind.CRITERION_CARD
    assert spec.statement == node.mastery_criteria[0].statement


def test_the_same_concept_taught_fresh_still_gets_the_explain_back() -> None:
    """The other half of the pair. The skip above is about *remediation*, not about EXPLAIN
    criteria — a first pass at an explain-shaped concept should still ask for it in their own
    words, or the rule would have quietly removed a surface rather than reordered one."""
    # Act
    spec = _selected(_move(), node=_node(kind=MasteryCriterionKind.EXPLAIN, misconceptions=[]))

    # Assert
    assert spec.kind is SurfaceKind.EXPLAIN_BACK


def test_a_move_that_names_a_concept_without_one_is_refused_rather_than_guessed() -> None:
    """``select_surface`` is exported, so ``take_turn`` is not the only thing that can call it.

    Treating a missing concept as "this must be a close" would hand a caller a mastery meter where
    an assessment card belonged, with nothing anywhere saying so — the silent wrong-instrument
    failure plan §8's "a broken assessment surface corrupts data" is about.
    """
    # Act / Assert
    with pytest.raises(ValueError, match="introduce"):
        select_surface(
            _move(),
            None,
            graph=_graph(),
            criterion=None,
            model=LearnerModel(graph_id="g1"),
            clock=_clock(),
        )


def test_a_misconception_that_repeats_the_definition_is_not_offered_twice() -> None:
    """Authoring quality is Phase 1's problem; an ambiguous question is this one's.

    If a misconception comes back textually identical to the definition, the card would offer the
    same words twice and "pick the true one" stops having a single answer — while the learner's
    choice is still graded as though it did.
    """
    # Arrange
    node = _node(misconceptions=["What gradient actually is.", "A gradient points uphill."])
    assert node.definition == "What gradient actually is.", "the fixture must actually collide"

    # Act
    spec = _selected(_move(MoveKind.REMEDIATE), node=node)

    # Assert
    assert spec.kind is SurfaceKind.QUIZ_CARD
    assert len(spec.options) == len(set(spec.options)) == 2


# ── the same rules, reached through the real director rather than a hand-built move ────────────


async def test_a_learner_who_is_genuinely_stuck_is_handed_the_quiz() -> None:
    """The quiz path end to end, and the gap review found in this file's first pass.

    Every other test here hands ``select_surface`` a ``DirectorMove`` built by hand, which proves
    the rule and nothing about the wiring. A REMEDIATE only happens for real after two misses on one
    concept, and the arguments the loop passes at that call site — the node, the criterion staged
    on *this* turn, the belief as it stands after the second miss — are exactly what a defect would
    get wrong while every isolated test stayed green.
    """
    # Arrange — a shrug, then the same shrug again.
    graph = _graph(_node(), _node("beta"))
    opened = await open_session(
        graph,
        LearnerModel(graph_id="g1"),
        _clock(turn=1),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )
    first = await _took(opened, graph, LearnerModel(graph_id="g1"), "No idea, sorry.", run_id="r2")

    # Act
    second = await _took(first.session, graph, first.model, "Still no idea.", run_id="r3")

    # Assert — the director really remediated, and the card followed it.
    standing = second.session.turns[-1]
    assert standing.move.kind is MoveKind.REMEDIATE
    assert standing.surface is not None
    assert standing.surface.kind is SurfaceKind.QUIZ_CARD
    assert standing.surface.node_id == standing.move.node_id, (
        "the card must be about the concept the director named, not the one before it"
    )
    assert set(_MISCONCEPTIONS) < set(standing.surface.options)


async def _took(session, graph, model, answer: str, *, run_id: str):
    return await take_turn(
        session,
        graph,
        model,
        answer=answer,
        answering_seq=session.turns[-1].seq,
        grader=StubGrader(),
        tutor=StubTutor(),
        run_id=run_id,
        elapsed_s=1.0,
        budget_s=1800.0,
    )


# ── the competitions between rules, and the branches nothing else reaches ──────────────────────


def test_a_stuck_learner_is_quizzed_even_when_the_concept_cannot_be_checked() -> None:
    """The one place two rules genuinely compete, so the order between them is a decision.

    A concept whose criteria all need a simulator would otherwise take rule 4's concept map — but a
    learner who has missed it twice is better served by seeing the wrong models they may be holding
    than by being shown where it sits on a map. Rule 3 is ahead of rule 4 for that reason, and this
    is the only input that can tell the two orderings apart.
    """
    # Arrange
    node = _node(needs_sim=True)

    # Act
    spec = _selected(_move(MoveKind.REMEDIATE), node=node)

    # Assert
    assert spec.kind is SurfaceKind.QUIZ_CARD


def test_a_criterion_asking_them_to_manipulate_something_still_gets_the_do_statement() -> None:
    """The third criterion kind, which nothing else in this file drives. ``MANIPULATE`` normally
    carries ``needs_sim`` and never reaches here — but the kinds and the flag are independent
    fields, so a map that authors one without the other must not fall off the end of the rules."""
    # Act
    spec = _selected(_move(), node=_node(kind=MasteryCriterionKind.MANIPULATE))

    # Assert
    assert spec.kind is SurfaceKind.CRITERION_CARD
    assert spec.asks is MasteryCriterionKind.MANIPULATE


def test_the_quiz_carries_nothing_but_the_question_and_the_options() -> None:
    """Pinned as the *exact* field set rather than as an absence of the words "answer" and
    "correct". A future field called ``truth_index`` or ``solution`` would carry precisely the leak
    this exists to prevent and would sail past a substring check."""
    # Act
    spec = _selected(_move(MoveKind.REMEDIATE))

    # Assert
    assert set(spec.model_dump()) == {"kind", "node_id", "concept", "question", "options"}


def test_two_processes_choose_the_same_card_for_the_same_learner() -> None:
    """The claim the in-process test cannot make, and the one that actually matters.

    "The same move yields the same spec" is a statement about two *learners*, who are served by two
    replicas in different processes. Comparing five calls inside one interpreter cannot see the
    failure that would break that: anything seeded once per process — ``hash()`` of a string, which
    Python salts per interpreter, a module-level uuid, a cached shuffle. Today's ordering keys on
    ``blake2b`` of the option's own text, which is why this passes; the point of the test is that
    the next person to touch it cannot quietly switch to something process-local.
    """
    # Arrange — the same selection, run under two different hash seeds.
    script = (
        "from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion, "
        "MasteryCriterionKind, TeachingSpec\n"
        "from lunaris_live.session import DirectorMove, LearnerModel, MoveKind, SessionClock, "
        "select_surface\n"
        "node = ConceptNode(id='gradient', name='Gradient', definition='What it is.',\n"
        "    teaching_spec=TeachingSpec(objective='Use it.', misconceptions=['Wrong one.', "
        "'Another wrong one.', 'A third.']),\n"
        "    mastery_criteria=[MasteryCriterion(kind=MasteryCriterionKind.PREDICT, "
        "statement='Say which way.')])\n"
        "graph = ConceptGraph(graph_id='g1', topic='T', nodes=[node], topo_order=['gradient'], "
        "is_acyclic=True)\n"
        "spec = select_surface(\n"
        "    DirectorMove(kind=MoveKind.REMEDIATE, node_id='gradient', reason='Stuck.'),\n"
        "    node, graph=graph, criterion=node.mastery_criteria[0],\n"
        "    model=LearnerModel(graph_id='g1'),\n"
        "    clock=SessionClock(turn=3, elapsed_s=1.0, budget_s=1800.0))\n"
        "print(spec.model_dump_json())\n"
    )

    # Act
    runs = [
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("0", "12345")
    ]

    # Assert — byte for byte, including the order of the options.
    assert runs[0] == runs[1], f"two processes disagreed:\n{runs[0]}\n{runs[1]}"
    assert "Another wrong one." in runs[0], "the fixture must actually produce a quiz"
