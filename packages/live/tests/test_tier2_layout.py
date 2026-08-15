"""Tier 2: the lesson is composed per learner, from a catalog nothing can step outside (P2b, T5).

Plan §8 names this tier's claim in one sentence: *"Lesson layouts composed per learner per moment:
worked example expanded or collapsed, hint drawer suppressed at high confidence, practice
scaffolding sized to the knowledge estimate. This tier is where 'the lesson is rendered at runtime'
is literally true — same node, different composition for different learners."*

So the load-bearing test is the opposite of Tier 1's. There, the same state must always yield the
same instrument. Here, **the same concept must yield a different arrangement to two learners who
know different amounts** — and if it does not, the tier is decorative.

The second claim is R6's: the composition is drawn from an **allow-list**, never from free-form
markup. That is enforced by making anything outside the catalog unrepresentable rather than by
checking for it, so these tests pin the catalog's own shape and the layout's internal consistency.
"""

import asyncio

import pytest
from lunaris_live.graph import (
    ConceptGraph,
    ConceptNode,
    MasteryCriterion,
    MasteryCriterionKind,
    TeachingSpec,
)
from lunaris_live.session import (
    DECAYED,
    MASTERED,
    LayoutComponent,
    LayoutSpec,
    LearnerModel,
    LessonParts,
    NodeKnowledge,
    SessionClock,
    StubTutor,
    WorkedExample,
    compose_layout,
    open_session,
)

_NODE_ID = "gradient"
_GRAPH_ID = "graph-1"


def _parts() -> LessonParts:
    """Everything the tutor could hand the composer, so what varies is the arrangement alone."""
    return LessonParts(
        worked_example=WorkedExample(
            title="Rolling downhill, one step",
            steps=[
                "Start at a point on the curve.",
                "Read the slope there.",
                "Step against it.",
            ],
        ),
        hint="The sign tells you the direction, the size tells you how far.",
        practice=[
            "Which way does the weight move when the slope is positive?",
            "What happens at a flat spot?",
            "Why divide by the batch size?",
        ],
    )


def _knowing(estimate: float, *, at_turn: int = 1) -> LearnerModel:
    return LearnerModel(
        graph_id=_GRAPH_ID,
        nodes={
            _NODE_ID: NodeKnowledge(
                node_id=_NODE_ID,
                estimate=estimate,
                evidence_count=2,
                last_evidence_turn=at_turn,
            )
        },
    )


def _clock(turn: int = 1) -> SessionClock:
    return SessionClock(turn=turn, elapsed_s=10.0, budget_s=900.0)


def _laid_out(model: LearnerModel, *, parts: LessonParts | None = None) -> LayoutSpec:
    return compose_layout(parts if parts is not None else _parts(), node_id=_NODE_ID, model=model)


def _components(layout: LayoutSpec) -> list[LayoutComponent]:
    return [block.component for block in layout.blocks]


def _block(layout: LayoutSpec, component: LayoutComponent):
    return next(block for block in layout.blocks if block.component is component)


# --- the tier's own claim ------------------------------------------------------------------------


def test_the_same_concept_is_composed_differently_for_two_learners() -> None:
    """T5's RED assertion, and the whole reason this tier exists.

    Two learners, the same concept, the same material from the tutor, the same turn — and the only
    thing that differs is what each of them is believed to know. If the arrangements come back equal
    then "the lesson is rendered at runtime" is a claim the product cannot make.
    """
    new_to_it = _laid_out(_knowing(0.2))
    has_it = _laid_out(_knowing(0.9))

    assert new_to_it != has_it
    assert _components(new_to_it) != _components(has_it)


def test_a_learner_new_to_the_concept_gets_the_worked_example_open() -> None:
    layout = _laid_out(_knowing(0.2))

    example = _block(layout, LayoutComponent.WORKED_EXAMPLE)
    assert example.expanded is True
    assert example.steps == _parts().worked_example.steps


def test_a_learner_part_way_there_gets_the_worked_example_collapsed() -> None:
    """The middle band: the example is still offered, but it opens closed.

    Between the director's two thresholds the learner has met this and has not mastered it, so the
    material stays within reach without the turn re-teaching what they half hold.
    """
    layout = _laid_out(_knowing(0.5))

    assert _block(layout, LayoutComponent.WORKED_EXAMPLE).expanded is False


def test_a_learner_who_has_the_concept_is_not_shown_a_worked_example_at_all() -> None:
    layout = _laid_out(_knowing(0.9))

    assert LayoutComponent.WORKED_EXAMPLE not in _components(layout)


def test_the_hint_drawer_is_suppressed_at_high_confidence() -> None:
    """Plan §8, verbatim. A hint offered to somebody who has the concept is noise at best, and at
    worst it tells them the system does not believe them."""
    assert LayoutComponent.HINT in _components(_laid_out(_knowing(0.2)))
    assert LayoutComponent.HINT in _components(_laid_out(_knowing(0.5)))
    assert LayoutComponent.HINT not in _components(_laid_out(_knowing(0.9)))


def test_practice_scaffolding_is_sized_to_the_knowledge_estimate() -> None:
    """Sized, not merely present or absent — three bands, three amounts."""
    struggling = _block(_laid_out(_knowing(0.2)), LayoutComponent.PRACTICE)
    assert struggling.prompts == _parts().practice

    part_way = _block(_laid_out(_knowing(0.5)), LayoutComponent.PRACTICE)
    assert part_way.prompts == _parts().practice[:1]

    assert LayoutComponent.PRACTICE not in _components(_laid_out(_knowing(0.9)))


def test_the_bands_are_the_director_s_own_thresholds() -> None:
    """The layout and the director must not disagree about what "has it" means.

    A learner the director considers to have mastered a concept, being shown the scaffolding for
    somebody who has not, is the two rule sets keying off different numbers — which is exactly the
    drift that makes an adaptive system feel arbitrary.
    """
    assert LayoutComponent.WORKED_EXAMPLE not in _components(_laid_out(_knowing(MASTERED)))
    assert LayoutComponent.WORKED_EXAMPLE in _components(_laid_out(_knowing(MASTERED - 0.001)))
    at_the_line = _block(_laid_out(_knowing(DECAYED)), LayoutComponent.WORKED_EXAMPLE)
    just_under = _block(_laid_out(_knowing(DECAYED - 0.001)), LayoutComponent.WORKED_EXAMPLE)
    assert at_the_line.expanded is False
    assert just_under.expanded is True


def test_what_was_earned_is_judged_undecayed_so_a_fresh_answer_is_not_forgotten() -> None:
    """The convention ``decide_move`` states, applied here: what was *earned* is read off the stored
    belief, what has *faded* off the decayed recall. Scaffolding asks what somebody has shown.

    Not a preference — it is the difference between the middle band existing and not. One met answer
    lands the belief exactly at ``DECAYED``, and a single turn of decay puts it back under, so a
    composer reading the decayed value would hand a beginner's lesson to a learner who had
    demonstrated the concept one turn earlier. Found by driving the real loop, in
    ``apps/api/tests/live/test_live_agui_layout.py``, which is where it stays pinned end to end.
    """
    just_answered = LearnerModel(
        graph_id=_GRAPH_ID,
        nodes={
            _NODE_ID: NodeKnowledge(
                node_id=_NODE_ID, estimate=DECAYED, evidence_count=1, last_evidence_turn=1
            )
        },
    )
    layout = compose_layout(_parts(), node_id=_NODE_ID, model=just_answered)

    assert _block(layout, LayoutComponent.WORKED_EXAMPLE).expanded is False


def test_a_faded_concept_is_not_re_scaffolded_when_the_director_comes_back_to_it() -> None:
    """A concept demonstrated forty turns ago still counts as demonstrated.

    The director answers fading by *retrieving* — asking the learner to produce it — and a retrieval
    arriving wrapped in a worked example and a hint would be the re-explanation the move exists to
    avoid (``select_surface`` rule 2 refuses the same substitution). So the lean layout here is the
    point rather than an oversight, and it is also where the top band earns its place: on a taught
    turn it is reachable only this way, because the director never re-teaches what it believes is
    held.
    """
    long_ago = LearnerModel(
        graph_id=_GRAPH_ID,
        nodes={
            _NODE_ID: NodeKnowledge(
                node_id=_NODE_ID, estimate=0.9, evidence_count=2, last_evidence_turn=1
            )
        },
    )
    layout = compose_layout(_parts(), node_id=_NODE_ID, model=long_ago)

    assert LayoutComponent.WORKED_EXAMPLE not in _components(layout)
    assert LayoutComponent.HINT not in _components(layout)


# --- what the layout always is ---------------------------------------------------------------


def test_the_lesson_and_the_card_are_always_in_the_layout() -> None:
    """Slots, not copies. The prose and the Tier 1 card already live on the turn, and a layout
    carrying its own second copy of either would be free to disagree with them."""
    for estimate in (0.0, 0.2, 0.5, 0.9, 1.0):
        components = _components(_laid_out(_knowing(estimate)))
        assert LayoutComponent.PROSE in components
        assert LayoutComponent.SURFACE in components


def test_the_card_comes_after_the_material_that_prepares_it() -> None:
    """Order is the composition. A question placed above the worked example that sets it up is a
    different lesson from the same parts in the other order."""
    layout = _laid_out(_knowing(0.2))
    order = _block(layout, LayoutComponent.STACK).children
    seen = {block.id: block.component for block in layout.blocks}
    sequence = [seen[child] for child in order]

    assert sequence.index(LayoutComponent.PROSE) < sequence.index(LayoutComponent.WORKED_EXAMPLE)
    assert sequence.index(LayoutComponent.WORKED_EXAMPLE) < sequence.index(LayoutComponent.PRACTICE)
    assert sequence.index(LayoutComponent.PRACTICE) < sequence.index(LayoutComponent.SURFACE)
    assert sequence.index(LayoutComponent.SURFACE) < sequence.index(LayoutComponent.HINT)


def test_a_tutor_that_offered_nothing_still_yields_a_usable_lesson() -> None:
    """The material is generative and the arrangement is not, so a failed illustration costs the
    trimmings and never the turn: the words and the card are still there, in order."""
    layout = _laid_out(_knowing(0.1), parts=LessonParts())

    assert _components(layout) == [
        LayoutComponent.STACK,
        LayoutComponent.PROSE,
        LayoutComponent.SURFACE,
    ]


def test_a_close_has_no_concept_and_is_composed_anyway() -> None:
    """A closing turn names no node, so there is no recall to read. It gets the lean layout rather
    than an exception — the meter is still a card, and the goodbye is still prose."""
    layout = compose_layout(LessonParts(), node_id=None, model=LearnerModel(graph_id=_GRAPH_ID))

    assert _components(layout) == [
        LayoutComponent.STACK,
        LayoutComponent.PROSE,
        LayoutComponent.SURFACE,
    ]


def test_a_concept_with_no_evidence_gets_the_fullest_scaffolding() -> None:
    """The belief about an unseen concept is 0.0, and the safe direction to be wrong in is assuming
    they have not got it — the same asymmetry ``recall_of`` itself is built on."""
    layout = compose_layout(_parts(), node_id=_NODE_ID, model=LearnerModel(graph_id=_GRAPH_ID))

    assert _block(layout, LayoutComponent.WORKED_EXAMPLE).expanded is True
    assert LayoutComponent.HINT in _components(layout)


# --- the layout cannot describe something that will not render --------------------------------


def test_every_block_is_reachable_from_the_root() -> None:
    for estimate in (0.0, 0.5, 0.9):
        layout = _laid_out(_knowing(estimate))
        reachable = set(_block(layout, LayoutComponent.STACK).children) | {"root"}
        assert {block.id for block in layout.blocks} == reachable


def test_a_layout_naming_a_child_it_does_not_contain_is_refused() -> None:
    with pytest.raises(ValueError, match="ghost"):
        LayoutSpec.model_validate(
            {"blocks": [{"id": "root", "component": "Stack", "children": ["ghost"]}]}
        )


def test_a_layout_with_no_root_is_refused() -> None:
    """Matched on the guard's own words, not merely on "root".

    Without that, deleting this check passes anyway: the reachability walk starts at ``root`` and
    reports a missing child using the same word, so a laxer assertion is satisfied by a *different*
    guard firing — and the diagnosis a reader gets is the wrong one.
    """
    with pytest.raises(ValueError, match="a layout needs a block with id"):
        LayoutSpec.model_validate({"blocks": [{"id": "prose", "component": "Prose"}]})


def test_a_layout_carrying_a_block_nothing_points_at_is_refused() -> None:
    """The quieter half of the same rule. A dangling child is a hole the renderer draws nothing
    into; a stranded block is material the composer meant to show and nobody will ever see — and
    only one of the two is visible from the screen it produces."""
    with pytest.raises(ValueError, match="nothing points at"):
        LayoutSpec.model_validate(
            {
                "blocks": [
                    {"id": "root", "component": "Stack", "children": ["prose"]},
                    {"id": "prose", "component": "Prose"},
                    {"id": "orphan", "component": "Hint", "hint": "Nobody will read this."},
                ]
            }
        )


def test_a_layout_reusing_one_id_is_refused() -> None:
    with pytest.raises(ValueError, match="twice"):
        LayoutSpec.model_validate(
            {
                "blocks": [
                    {"id": "root", "component": "Stack", "children": ["p"]},
                    {"id": "p", "component": "Prose"},
                    {"id": "p", "component": "Hint", "hint": "..."},
                ]
            }
        )


def test_a_component_outside_the_catalog_cannot_be_expressed() -> None:
    """R6's allow-list, enforced by the type rather than by a check. A tutor — or anything else
    that ever composes a layout — writing free-form markup fails to parse, which is what makes the
    catalog a boundary instead of a convention."""
    with pytest.raises(ValueError):
        LayoutSpec.model_validate(
            {
                "blocks": [
                    {"id": "root", "component": "Stack", "children": ["x"]},
                    {"id": "x", "component": "IframeEmbed", "src": "https://example.com"},
                ]
            }
        )


def test_the_allow_list_is_exactly_these_six_names() -> None:
    """The catalog, pinned as literals — and the web suite pins the same six from its side.

    This is a contract between two separately deployed things, so it gets the treatment T1 and T3
    gave the mount path and the tool names: a literal on each side rather than a shared import,
    because a shared symbol only proves agreement at commit time and says nothing about which build
    is running where. Drift here is the quiet failure — a component the server composes and the
    browser has never heard of renders as nothing, and the run looks perfect from the server.
    """
    assert {member.value for member in LayoutComponent} == {
        "Stack",
        "Prose",
        "Surface",
        "WorkedExample",
        "Hint",
        "Practice",
    }
    assert LayoutSpec.CATALOG == "lunaris.live.layout/v1"


# --- determinism, since the arrangement is not the model's to choose ---------------------------


def test_the_same_learner_is_composed_the_same_way_every_time() -> None:
    model = _knowing(0.3)
    once = _laid_out(model)
    assert all(_laid_out(model) == once for _ in range(5))


def test_composition_asks_nothing_generative() -> None:
    """The parameter set is the guarantee, the same way ``select_surface``'s is (AD18). A tutor, a
    grader or a client threaded in here would make the arrangement a thing a model could move, and
    the two-learner claim above would stop being checkable."""
    from inspect import signature

    assert set(signature(compose_layout).parameters) == {"parts", "node_id", "model"}


def test_the_parts_are_the_tutors_words_unedited() -> None:
    """The composer arranges; it does not rewrite. A hint paraphrased on the way through would be a
    second author nobody can see, in the one place the material is supposed to be the tutor's."""
    parts = _parts()
    layout = _laid_out(_knowing(0.2), parts=parts)

    assert _block(layout, LayoutComponent.HINT).hint == parts.hint
    example = _block(layout, LayoutComponent.WORKED_EXAMPLE)
    assert example.title == parts.worked_example.title
    assert example.steps == parts.worked_example.steps


def test_a_criterion_the_learner_is_marked_on_is_not_copied_into_the_layout() -> None:
    """The card is a slot for exactly this reason: two renderings of the do-statement is two
    statements, and the learner is marked against one of them."""
    layout = _laid_out(_knowing(0.2))
    assert "Say which way a weight should move" not in layout.model_dump_json()


# --- through the loop, where the material is generative and the arrangement is not ---------------


class _SilentTutor(StubTutor):
    """A tutor that teaches normally and cannot illustrate. The failure T5 has to survive."""

    async def illustrate(self, *args: object, **kwargs: object) -> LessonParts:
        raise RuntimeError("no provider for the trimmings")


class _SlowTutor(StubTutor):
    """A tutor whose illustration never arrives. Indistinguishable from a hung provider, which is
    the point: the turn must not wait on material it can go without."""

    async def illustrate(self, *args: object, **kwargs: object) -> LessonParts:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")


def _graph() -> ConceptGraph:
    return ConceptGraph(
        graph_id=_GRAPH_ID,
        topic="Gradient descent",
        nodes=[
            ConceptNode(
                id=_NODE_ID,
                name="Gradient",
                definition="The direction of steepest increase.",
                requires=[],
                teaching_spec=TeachingSpec(
                    objective="Say which way a weight should move.",
                    misconceptions=["A gradient points uphill, towards the answer."],
                ),
                mastery_criteria=[
                    MasteryCriterion(
                        kind=MasteryCriterionKind.PREDICT,
                        statement="Say which way a weight should move.",
                    )
                ],
            )
        ],
        topo_order=[_NODE_ID],
    )


async def _opened(tutor: StubTutor) -> object:
    return await open_session(
        _graph(),
        LearnerModel(graph_id=_GRAPH_ID),
        _clock(),
        session_id="s-1",
        run_id="r-1",
        tutor=tutor,
    )


@pytest.mark.asyncio
async def test_a_turn_taken_through_the_loop_is_laid_out() -> None:
    """The layout is on the turn, recorded rather than derived on read — the same call AD15 made
    for the Tier 1 card, and for the same reason: re-deriving it would be a second implementation
    of the rules, free to disagree with the one the learner actually saw."""
    session = await _opened(StubTutor())

    layout = session.turns[-1].layout
    assert layout is not None
    assert LayoutComponent.PROSE in _components(layout)
    assert LayoutComponent.SURFACE in _components(layout)


@pytest.mark.asyncio
async def test_the_tutors_material_reaches_the_layout_through_the_real_loop() -> None:
    """Not asserted on a hand-built ``LessonParts``: what a defect would break is the wiring at
    the call site — that the tutor is asked about *this* node, and that what it wrote arrives
    unedited."""
    session = await _opened(StubTutor())

    layout = session.turns[-1].layout
    assert layout is not None
    assert "Gradient" in _block(layout, LayoutComponent.WORKED_EXAMPLE).title
    assert "points uphill" in _block(layout, LayoutComponent.HINT).hint


@pytest.mark.asyncio
async def test_an_illustration_that_fails_does_not_cost_the_turn() -> None:
    session = await _opened(_SilentTutor())

    turn = session.turns[-1]
    assert turn.tutor
    assert turn.surface is not None
    assert _components(turn.layout) == [
        LayoutComponent.STACK,
        LayoutComponent.PROSE,
        LayoutComponent.SURFACE,
    ]


@pytest.mark.asyncio
async def test_an_illustration_that_never_arrives_does_not_hold_the_turn() -> None:
    """Bounded, and the bound is what is under test: a tutor sleeping for an hour must not keep a
    learner waiting for a hint drawer. The turn comes back with the lesson and the card."""
    async with asyncio.timeout(5):
        session = await _opened(_SlowTutor())

    assert _components(session.turns[-1].layout) == [
        LayoutComponent.STACK,
        LayoutComponent.PROSE,
        LayoutComponent.SURFACE,
    ]


class _TutorThatNeedsBothCallsAtOnce(StubTutor):
    """A tutor whose two calls can only finish if they are in flight *at the same moment*.

    A **rendezvous**, not a start flag, and the difference is the whole test. ``teach`` announces
    itself and then blocks until ``illustrate`` has answered; ``illustrate`` waits for that
    announcement before answering. Neither can complete alone, so a caller that awaits one and then
    the other deadlocks — **in either order** — and the outer timeout fails the test.

    The first version of this fixture set its flag at the top of ``teach`` and was worthless: that
    is satisfied the instant ``illustrate`` is called *after* ``teach`` has been called at all,
    which is exactly what a sequential implementation does. It was caught by a reviewer rewriting
    the production code to two plain awaits and watching the test stay green — the fourth time this
    journey has shipped a green test that could not fail, and the second time the cause was a claim
    about *timing* being checked by an assertion about *outcome*.
    """

    def __init__(self) -> None:
        self.speaking = asyncio.Event()
        self.illustrated = asyncio.Event()

    async def teach(self, *args: object, **kwargs: object) -> str:
        self.speaking.set()
        # Blocks until the material has been written. A sequential caller reaches here with nothing
        # else running, and nothing will ever set this.
        await self.illustrated.wait()
        return await super().teach(*args, **kwargs)  # type: ignore[arg-type]

    async def illustrate(self, *args: object, **kwargs: object) -> LessonParts:
        await self.speaking.wait()
        parts = await super().illustrate(*args, **kwargs)  # type: ignore[arg-type]
        self.illustrated.set()
        return parts


@pytest.mark.asyncio
async def test_the_material_is_written_beside_the_lesson_not_after_it() -> None:
    """Tier 2 is allowed to cost money and it is not allowed to cost time.

    The material does not depend on the lesson's words — the layout holds a *slot* for them, never a
    copy — so a second call made after the first finishes would add its whole latency to every turn
    for something the turn can go without.
    """
    tutor = _TutorThatNeedsBothCallsAtOnce()

    # The bound is what turns a deadlock into a failing assertion rather than a hung suite.
    async with asyncio.timeout(5):
        session = await _opened(tutor)

    assert LayoutComponent.WORKED_EXAMPLE in _components(session.turns[-1].layout)
