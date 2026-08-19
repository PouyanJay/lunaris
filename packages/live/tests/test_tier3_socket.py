"""Tier 3: the socket a simulator plugs into, with nothing plugged into it yet (P2b, T6).

Plan §8's third tier is *"the concept simulators: self-contained interactive bundles rendered in
sandboxed iframes"*, and plan §9 is the factory that builds them. Neither is this task. What this
task owes is the **socket**: registration (something says this concept has a sim), mount (the turn
puts it on screen), and one event coming back (what the learner did reaches the loop). A3: "Phase 3
replaces the stub, not the socket."

The load-bearing decision, and the reason this is small: **a sim's report is an answer.** It is
graded where every other answer is — by the separate grader, against the criterion the turn staged
(U1). Inventing a second way for evidence to enter the learner model would be the mistake AD16
already refused for the quiz card, with a whole new surface behind it and no eval to check it.

So the concept this unlocks is the one P2a and T3 both had to leave stranded: a concept whose every
criterion needs a simulator could be *taught* and never *checked*, and the director could only hand
it a concept map and move on.
"""

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
    LearnerModel,
    MoveKind,
    SessionClock,
    SimApp,
    StubGrader,
    StubSimRegistry,
    StubTutor,
    SurfaceKind,
    open_session,
    select_surface,
    stage_criterion,
    take_turn,
)

_NODE_ID = "divergence"
_GRAPH_ID = "g1"
_BUDGET_S = 1800.0

#: Spelt out rather than escaped, because a literal backslash in a test URL is the entire subject
#: of one of these cases and an escape sequence is the easiest thing in the file to misread.
BACKSLASH = chr(92)
TAB = chr(9)

#: What a concept needing a simulator asks for. Not answerable in prose by design — that is the
#: whole reason the tier exists.
_SIM_STATEMENT = "Drive the learning rate up until the loss diverges, and say where it turned."


def _node(*, sim_only: bool = True) -> ConceptNode:
    """A concept whose only criterion needs a simulator, unless asked otherwise."""
    criteria = [
        MasteryCriterion(
            kind=MasteryCriterionKind.MANIPULATE, statement=_SIM_STATEMENT, needs_sim=True
        )
    ]
    if not sim_only:
        criteria.append(
            MasteryCriterion(
                kind=MasteryCriterionKind.EXPLAIN,
                statement="Explain divergence in your own words.",
                needs_sim=False,
            )
        )
    return ConceptNode(
        id=_NODE_ID,
        name="Divergence",
        definition="What happens when the steps get too big to settle.",
        teaching_spec=TeachingSpec(
            objective="Recognise divergence.", misconceptions=["A big step just learns faster."]
        ),
        mastery_criteria=criteria,
    )


def _graph() -> ConceptGraph:
    return ConceptGraph(
        graph_id=_GRAPH_ID,
        topic="How neural networks learn",
        nodes=[_node()],
        topo_order=[_NODE_ID],
        is_acyclic=True,
    )


def _clock(turn: int = 1) -> SessionClock:
    return SessionClock(turn=turn, elapsed_s=0.0, budget_s=_BUDGET_S)


# --- registration --------------------------------------------------------------------------------


def test_a_concept_that_needs_a_simulator_is_staged_when_one_is_registered() -> None:
    """T6's first claim. Without a registry this concept stages nothing and can never be checked;
    with one, the criterion the simulator exists to demonstrate is what the turn puts up."""
    staged = stage_criterion(_node(), sims=StubSimRegistry())

    assert staged is not None
    assert staged.needs_sim is True
    assert staged.statement == _SIM_STATEMENT


def test_without_a_registry_a_sim_only_concept_still_stages_nothing() -> None:
    """P2a's behaviour, unchanged and deliberately so. A criterion staged with no simulator behind
    it would ask a learner to demonstrate something they have been given no way to do."""
    assert stage_criterion(_node()) is None


def test_a_concept_answerable_in_prose_is_never_diverted_to_a_simulator() -> None:
    """The prose criterion wins even when a sim is available. A text answer graded by the separate
    grader is the evidence path this product has actually evaluated (P2a's keyed eval); routing
    around it because a sim happens to exist would trade a measured instrument for an unmeasured
    one."""
    staged = stage_criterion(_node(sim_only=False), sims=StubSimRegistry())

    assert staged is not None
    assert staged.needs_sim is False


def test_a_registry_with_nothing_for_this_concept_leaves_it_unchecked() -> None:
    """The state Phase 3 spends its time in: a real registry knows about the sims that have been
    built, and every other concept keeps P2a's honest "taught here, not checkable here"."""

    class EmptyRegistry:
        def app_for(self, node: ConceptNode, criterion: MasteryCriterion) -> SimApp | None:
            return None

    assert stage_criterion(_node(), sims=EmptyRegistry()) is None


def test_the_registry_refuses_a_criterion_a_text_answer_can_already_carry() -> None:
    """``app_for`` is asked directly, because through the loop this can never be reached: staging
    returns the prose criterion first and never consults the registry about it, and the surface rule
    requires ``needs_sim`` anyway. Two layers above make the guard invisible — which is exactly why
    it is worth pinning here rather than deleting.

    ``ISimRegistry`` is a public protocol, and what it promises is that a registry answers about
    simulators. Phase 3's registry is the one that matters: asked about a criterion a learner can
    simply write an answer to, it must decline, or the loop gains a way to route a measured
    instrument into an unmeasured one.
    """
    node = _node(sim_only=False)
    spoken = next(c for c in node.mastery_criteria if not c.needs_sim)

    assert StubSimRegistry().app_for(node, spoken) is None


# --- the mount -----------------------------------------------------------------------------------


def test_the_turn_mounts_the_simulator_the_registry_named() -> None:
    move = DirectorMove(kind=MoveKind.INTRODUCE, node_id=_NODE_ID, reason="Because.")
    node = _node()
    staged = stage_criterion(node, sims=StubSimRegistry())
    app = StubSimRegistry().app_for(node, staged)

    spec = select_surface(
        move,
        node,
        graph=_graph(),
        criterion=staged,
        model=LearnerModel(graph_id=_GRAPH_ID),
        clock=_clock(),
        sim=app,
    )

    assert spec.kind is SurfaceKind.SIM_APP
    assert spec.app_id == app.app_id
    assert spec.url == app.url
    assert spec.statement == _SIM_STATEMENT


def test_the_simulator_outranks_the_concept_map_it_replaces() -> None:
    """T3's rule 4 handed a concept-map card to any concept this session could not check, because
    nothing said next could move a belief. A mounted simulator is exactly the case where something
    *can*, so the rule that existed to be honest about the gap must not fire once the gap is
    closed."""
    move = DirectorMove(kind=MoveKind.INTRODUCE, node_id=_NODE_ID, reason="Because.")
    node = _node()

    without = select_surface(
        move,
        node,
        graph=_graph(),
        criterion=None,
        model=LearnerModel(graph_id=_GRAPH_ID),
        clock=_clock(),
        sim=None,
    )
    with_sim = select_surface(
        move,
        node,
        graph=_graph(),
        criterion=stage_criterion(node, sims=StubSimRegistry()),
        model=LearnerModel(graph_id=_GRAPH_ID),
        clock=_clock(),
        sim=StubSimRegistry().app_for(node, stage_criterion(node, sims=StubSimRegistry())),
    )

    assert without.kind is SurfaceKind.CONCEPT_MAP
    assert with_sim.kind is SurfaceKind.SIM_APP


def test_a_stuck_learner_gets_the_simulator_rather_than_a_quiz_about_it() -> None:
    """The one place two rules genuinely compete, and it is a correctness question rather than a
    pedagogical preference.

    Whatever card is shown, the answer it collects is graded against the criterion *this turn
    staged*. A misconception quiz shown while a simulator's do-statement is staged would have a
    picked option — "a big step just learns faster" — marked against "drive the learning rate up
    until the loss diverges". The verdict would be meaningless and the belief would move on it,
    which is precisely the corrupted assessment surface plan §8 exists to prevent.

    Reachable only since T6: before a simulator could be mounted, a sim-only concept could never be
    graded, so it could never accrue the evidence a remediation is decided from. The concept here
    has authored misconceptions, so the quiz genuinely *is* available and genuinely loses.
    """
    node = _node()
    assert node.teaching_spec is not None and node.teaching_spec.misconceptions, (
        "the fixture is only meaningful if a quiz is actually available to lose"
    )
    staged = stage_criterion(node, sims=StubSimRegistry())

    spec = select_surface(
        DirectorMove(kind=MoveKind.REMEDIATE, node_id=_NODE_ID, reason="Missed twice."),
        node,
        graph=_graph(),
        criterion=staged,
        model=LearnerModel(graph_id=_GRAPH_ID),
        clock=_clock(),
        sim=StubSimRegistry().app_for(node, staged),
    )

    assert spec.kind is SurfaceKind.SIM_APP


def test_a_stuck_learner_on_a_written_concept_still_gets_the_quiz() -> None:
    """The other side of the rule above: moving the simulator up must not take the quiz away from
    every concept that has no simulator, which is nearly all of them."""
    node = _node(sim_only=False)
    staged = stage_criterion(node, sims=StubSimRegistry())

    spec = select_surface(
        DirectorMove(kind=MoveKind.REMEDIATE, node_id=_NODE_ID, reason="Missed twice."),
        node,
        graph=_graph(),
        criterion=staged,
        model=LearnerModel(graph_id=_GRAPH_ID),
        clock=_clock(),
        sim=StubSimRegistry().app_for(node, staged),
    )

    assert spec.kind is SurfaceKind.QUIZ_CARD


def test_a_staged_sim_criterion_with_no_app_never_reaches_the_screen() -> None:
    """Belt and braces at the one seam where the two halves could disagree. Mounting a card that
    names no application would render an empty frame, which reads as a broken session rather than
    as a concept nobody has built a simulator for yet."""
    move = DirectorMove(kind=MoveKind.INTRODUCE, node_id=_NODE_ID, reason="Because.")
    node = _node()

    spec = select_surface(
        move,
        node,
        graph=_graph(),
        criterion=stage_criterion(node, sims=StubSimRegistry()),
        model=LearnerModel(graph_id=_GRAPH_ID),
        clock=_clock(),
        sim=None,
    )

    assert spec.kind is not SurfaceKind.SIM_APP


def test_the_card_carries_the_words_the_learner_will_be_marked_against() -> None:
    """Same rule the criterion card keeps: marked against one wording and shown another is an
    assessment of something nobody was asked."""
    node = _node()
    staged = stage_criterion(node, sims=StubSimRegistry())

    spec = select_surface(
        DirectorMove(kind=MoveKind.INTRODUCE, node_id=_NODE_ID, reason="Because."),
        node,
        graph=_graph(),
        criterion=staged,
        model=LearnerModel(graph_id=_GRAPH_ID),
        clock=_clock(),
        sim=StubSimRegistry().app_for(node, staged),
    )

    assert spec.statement == staged.statement


# --- the round trip ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_session_opens_on_a_concept_only_a_simulator_can_check() -> None:
    """The whole point of the socket, end to end through the real loop: a map that P2a could only
    talk about now opens with something the learner can act in."""
    session = await open_session(
        _graph(),
        LearnerModel(graph_id=_GRAPH_ID),
        _clock(),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
        sims=StubSimRegistry(),
    )

    standing = session.turns[-1]
    assert standing.surface is not None
    assert standing.surface.kind is SurfaceKind.SIM_APP
    assert standing.criterion is not None
    assert standing.criterion.needs_sim is True


@pytest.mark.asyncio
async def test_what_the_simulator_reports_is_graded_like_any_other_answer() -> None:
    """The load-bearing decision, driven rather than argued. The sim's report goes in through the
    answer path, is scored by the *same separate grader* against the *same staged criterion*, and
    moves the belief the same way — so Tier 3 adds a surface and not a second way to be assessed.
    """
    session = await open_session(
        _graph(),
        LearnerModel(graph_id=_GRAPH_ID),
        _clock(),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
        sims=StubSimRegistry(),
    )

    outcome = await take_turn(
        session,
        _graph(),
        LearnerModel(graph_id=_GRAPH_ID),
        answer=(
            "Drove the learning rate up until the loss diverges; it turned at about 0.9 "
            "and the loss climbed away."
        ),
        answering_seq=session.turns[-1].seq,
        grader=StubGrader(),
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
        sims=StubSimRegistry(),
    )

    answered = outcome.session.turns[0]
    assert answered.grade is not None
    assert outcome.model.nodes[_NODE_ID].evidence_count == 1
    assert outcome.model.nodes[_NODE_ID].estimate > 0.0


@pytest.mark.asyncio
async def test_a_session_without_a_registry_behaves_exactly_as_it_did_before() -> None:
    """P2a and every session already stored. The registry is optional at the seam, so a deployment
    with no sims — which is every deployment today — is not a deployment with a broken loop."""
    session = await open_session(
        _graph(),
        LearnerModel(graph_id=_GRAPH_ID),
        _clock(),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )

    standing = session.turns[-1]
    assert standing.criterion is None
    assert standing.surface is not None
    assert standing.surface.kind is SurfaceKind.CONCEPT_MAP


# --- what the socket refuses ---------------------------------------------------------------------


def test_a_simulator_must_name_somewhere_to_load_from() -> None:
    """The mount takes a URL from day one, so Phase 3 plugs in a built bundle rather than
    redesigning the socket around one."""
    with pytest.raises(ValueError):
        SimApp(app_id="stub", url="", title="A simulator")


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        # Protocol-relative: it looks like a path, parses with an empty scheme, and loads from
        # another host entirely - the one shape a naive "starts with a slash" check waves through.
        "//evil.example/sim.html",
    ],
)
def test_a_simulator_is_never_loaded_from_a_scheme_a_frame_should_not_run(url: str) -> None:
    """A registry entry is data, and Phase 3's will be written by a builder agent. A ``javascript:``
    or ``data:`` source in a frame is script running with whatever the frame is trusted with, so the
    refusal belongs at the contract rather than in whichever renderer happens to read it."""
    with pytest.raises(ValueError):
        SimApp(app_id="stub", url=url, title="A simulator")


@pytest.mark.parametrize(
    "url",
    [
        "/" + BACKSLASH + "evil.example",
        "/" + BACKSLASH + "/evil.example",
        # A browser strips tabs from a URL before parsing, so this is the same trick wearing a
        # disguise. ``urlparse`` strips it too, which is why the pattern must refuse what is left.
        "/" + TAB + BACKSLASH + "evil.example",
    ],
)
def test_a_path_a_browser_would_read_as_another_host_is_refused(url: str) -> None:
    """The bypass that got through the first version of this guard, and the reason it is now an
    allow-list.

    ``urlparse`` reads a backslash as an ordinary path character; the URL spec folds it into a
    slash for http(s). So a registry entry of ``/`` + backslash + ``evil.example`` looks like an
    inert same-origin path to every Python check and resolves, in the browser that actually sets
    ``iframe.src``, to ``https://evil.example/``. Verified against Node's ``new URL`` before and
    after the fix.

    This matters precisely because Phase 3's registry is written by a builder agent: the guard has
    to hold against generated data, not just against the one hard-coded entry it serves today.
    """
    with pytest.raises(ValueError):
        SimApp(app_id="stub", url=url, title="A simulator")


def test_a_simulator_may_be_mounted_from_a_same_origin_path() -> None:
    """What the stub actually uses. The API composing a session does not reliably know which origin
    a browser reached it on, and a same-origin path needs no such guess."""
    assert SimApp(app_id="stub", url="/api/live/sims/stub", title="A simulator").url


def test_the_shapes_phase_three_will_actually_need_are_still_allowed() -> None:
    """The other half of an allow-list: it has to let through what the factory will produce. A
    guard tightened until nothing real fits is a guard somebody loosens in a hurry later."""
    for url in (
        "/api/live/sims/stub",
        "/api/live/sims/gradient-descent-v2?variant=b",
        "https://sims.lunaris.example/gradient/index.html",
        "http://127.0.0.1:8000/api/live/sims/stub",
    ):
        assert SimApp(app_id="stub", url=url, title="A simulator").url == url
