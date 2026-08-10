"""The tutor: how a director's move becomes something a learner actually reads (Phase 2a, T4).

The director decides *what* happens next and is deterministic by design; the tutor decides *how it
is said* and cannot be. So this is a seam with two implementations — a stub for the offline path and
a model-backed one for production — and these tests are about what the tutor does with a concept,
never about prose quality, which is T9's keyed eval.

The load-bearing claim is that the node's ``teaching_spec`` reaches the teaching. A tutor that only
knows what is true teaches *at* the learner; the misconceptions are what let it go looking for the
specific wrong model in front of it, and they are the whole reason Phase 1 paid a model call per
concept to author them. A tutor that ignored them would be indistinguishable from an encyclopaedia
and no test of the wiring alone would notice.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.graph import (
    ConceptNode,
    MasteryCriterion,
    MasteryCriterionKind,
    TeachingDepth,
    TeachingSpec,
)
from lunaris_live.session import (
    ClaudeTutor,
    DirectorMove,
    MoveKind,
    StubTutor,
    TutorUnavailableError,
)

_MISCONCEPTION = "A derivative is a formula to memorise, not a slope you can see."

_TEACHING = (
    "Picture the loss as a hillside you are standing on. The gradient is just which way is "
    "downhill from where you stand, and how steep it is. Which way would you step?"
)


def _node(*, spec: TeachingSpec | None = None) -> ConceptNode:
    return ConceptNode(
        id="gradient",
        name="Gradient",
        definition="The slope of the loss with respect to each weight.",
        teaching_spec=spec
        if spec is not None
        else TeachingSpec(
            objective="Say which way is downhill and how steep it is there.",
            misconceptions=[_MISCONCEPTION],
            depth=TeachingDepth.INTUITION_FIRST,
        ),
        mastery_criteria=[
            MasteryCriterion(
                kind=MasteryCriterionKind.PREDICT,
                statement="Point at a curve and say which way lowers it.",
            )
        ],
    )


def _move(kind: MoveKind = MoveKind.INTRODUCE) -> DirectorMove:
    return DirectorMove(kind=kind, node_id="gradient", reason="Because the test says so.")


class ScriptedModel:
    """Replays one response and records the prompts it was asked with."""

    def __init__(self, reply: str = _TEACHING) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content=self._reply)


async def _taught(
    model: object, *, move: DirectorMove | None = None, node: ConceptNode | None = None
) -> str:
    return await ClaudeTutor("m", client=model).teach(
        move or _move(),
        node or _node(),
        topic="How neural networks learn",
        run_id="r1",
    )


# ── the concept reaches the teaching ───────────────────────────────────────────────────────────


async def test_the_misconception_the_node_names_is_what_the_tutor_is_told_to_look_for() -> None:
    """The task's RED assertion. Phase 1 spends a model call per concept authoring these, and they
    exist for exactly one purpose: a tutor that knows how people get this wrong can hunt the wrong
    model in front of it instead of explaining into the air."""
    # Arrange
    model = ScriptedModel()

    # Act
    await _taught(model)

    # Assert — verbatim, not paraphrased: the tutor passes the authored text through rather than
    # summarising it, so what Phase 1 wrote is what the tutor reads.
    assert _MISCONCEPTION in model.prompts[0]


async def test_the_tutor_teaches_this_concept_and_not_the_map_around_it() -> None:
    # Arrange
    model = ScriptedModel()
    node = _node()

    # Act
    await _taught(model)

    # Assert — name, definition and objective all reach it. Without the objective the tutor knows
    # what the concept *is* but not what the learner is meant to be able to do with it, which is
    # the difference between a lecture and a lesson.
    prompt = model.prompts[0]
    assert node.name in prompt
    assert node.definition in prompt
    assert node.teaching_spec is not None
    assert node.teaching_spec.objective in prompt
    assert "How neural networks learn" in prompt


async def test_what_the_learner_reads_is_the_tutors_words_not_the_prompt() -> None:
    # Act
    taught = await _taught(ScriptedModel(f"  {_TEACHING}  "))

    # Assert — trimmed, and nothing else: a tutor that decorated the response would be putting
    # words in a teacher's mouth.
    assert taught == _TEACHING


async def test_a_concept_the_compiler_left_unspecified_is_still_teachable() -> None:
    """``teaching_spec`` is optional on purpose: one failed authoring call must not make a concept
    unteachable, only less well taught."""
    # Arrange
    model = ScriptedModel()
    bare = ConceptNode(id="gradient", name="Gradient", definition="The slope of the loss.")

    # Act
    taught = await _taught(model, node=bare)

    # Assert
    assert taught == _TEACHING
    assert "Gradient" in model.prompts[0]
    assert "The slope of the loss." in model.prompts[0]


# ── the move is what the tutor is doing ────────────────────────────────────────────────────────


async def test_every_teachable_move_asks_the_tutor_for_something_different() -> None:
    """The director's whole output is the move. A tutor that said the same thing for all three
    would make the policy decorative — the trace would show adaptation the learner never saw."""
    # Arrange
    model = ScriptedModel()

    # Act — every kind against the same concept, so the only difference is the move.
    for kind in (MoveKind.INTRODUCE, MoveKind.RETRIEVE, MoveKind.REMEDIATE):
        await _taught(model, move=_move(kind))

    # Assert — three prompts, pairwise distinct.
    assert len(set(model.prompts)) == 3


async def test_remediation_is_told_not_to_repeat_the_explanation_that_already_failed() -> None:
    """The director only remediates after two misses (``_STUCK_AFTER``). Saying the same thing
    louder is precisely what it is trying to avoid, so the instruction has to carry that.

    Asserted on the prohibition itself, not on "a different way" nearby: with the softer wording
    checked, the clause this test is named for could be deleted from the prompt outright and the
    test would stay green — which is the exact defect the T3 pass went looking for.
    """
    # Arrange
    model = ScriptedModel()

    # Act
    await _taught(model, move=_move(MoveKind.REMEDIATE))

    # Assert
    prompt = model.prompts[0].lower()
    assert "do not repeat the explanation they have already heard" in prompt
    assert "a different example" in prompt


async def test_retrieval_asks_the_learner_to_recall_rather_than_re_explaining() -> None:
    """Spaced retrieval only works if the learner does the retrieving. A tutor that re-taught the
    concept would leave the belief untouched and the director looping on it — so the prohibition,
    not the word "recall" beside it, is what has to be pinned."""
    # Arrange
    model = ScriptedModel()

    # Act
    await _taught(model, move=_move(MoveKind.RETRIEVE))

    # Assert
    prompt = model.prompts[0].lower()
    assert "do not re-explain it" in prompt
    assert "ask them to recall it" in prompt


async def test_closing_is_not_something_the_tutor_is_asked_to_teach() -> None:
    """A close is about the session, not a concept — the director sends it with no ``node_id`` at
    all. Handing it to the tutor as if it were a concept is a bug worth failing loudly on rather
    than teaching whatever node happened to be passed."""
    # Act / Assert
    with pytest.raises(ValueError):
        await _taught(ScriptedModel(), move=DirectorMove(kind=MoveKind.CLOSE, reason="Time is up."))


# ── not saying the same thing twice ────────────────────────────────────────────────────────────


async def test_the_tutor_is_told_what_it_has_already_said_about_this_concept() -> None:
    """Found by running a whole session (T5): the second turn on a concept came back as the first
    turn's words, verbatim. "Come at it a different way" is an instruction no tutor can follow
    without knowing which way it already came at it — the remediation prompt was asking for
    something the tutor had no way to do."""
    # Arrange
    model = ScriptedModel()
    first = "Picture the loss as a hillside you are standing on."

    # Act
    await ClaudeTutor("m", client=model).teach(
        _move(MoveKind.REMEDIATE),
        _node(),
        topic="How neural networks learn",
        already_said=[first],
        run_id="r1",
    )

    # Assert — the words themselves, and the prohibition that makes carrying them worth anything.
    prompt = model.prompts[0]
    assert first in prompt
    assert "do not re-use its analogy" in prompt.lower()


async def test_a_first_turn_on_a_concept_is_not_told_to_avoid_anything() -> None:
    """An empty history must not become an instruction about nothing — a tutor told not to repeat
    itself before it has said anything is being handed a puzzle instead of a concept."""
    # Arrange
    model = ScriptedModel()

    # Act
    await _taught(model)

    # Assert
    assert "already said" not in model.prompts[0].lower()


async def test_the_stub_does_not_repeat_itself_on_a_second_pass_either() -> None:
    """The offline path has to be able to show it, or a surface built and reviewed against the stub
    would pass over a tutor that says one thing forever."""
    # Arrange
    tutor = StubTutor()
    first = await tutor.teach(_move(), _node(), topic="A subject", run_id="r1")

    # Act
    second = await tutor.teach(
        _move(MoveKind.REMEDIATE),
        _node(),
        topic="A subject",
        already_said=[first],
        run_id="r2",
    )

    # Assert
    assert second != first
    assert second.startswith("Another way to see it.")


# ── staging what the learner will be marked on ─────────────────────────────────────────────────


async def test_the_turn_ends_by_asking_for_the_criterion_that_will_be_graded() -> None:
    """U1's mechanism: the tutor stages one of the concept's do-statements, the learner answers in
    prose, and a *separate* grader scores that answer against that same statement. If the tutor
    ends on a question of its own devising, the grader marks an answer to a question nobody
    recorded — and the belief that moves is about something else entirely."""
    # Arrange
    model = ScriptedModel()
    criterion = MasteryCriterion(
        kind=MasteryCriterionKind.PREDICT,
        statement="Say which way a weight should move to lower the loss.",
    )

    # Act
    await ClaudeTutor("m", client=model).teach(
        _move(), _node(), topic="How neural networks learn", criterion=criterion, run_id="r1"
    )

    # Assert — the statement verbatim, and the instruction that makes it the closing question.
    prompt = model.prompts[0]
    assert criterion.statement in prompt
    assert "end by asking them to do exactly this" in prompt.lower()


async def test_a_concept_with_nothing_checkable_still_ends_somewhere() -> None:
    """Every criterion needing a simulator (Phase 3) is a real state: the concept can be taught
    here and cannot be checked here. The turn still has to end on something a learner can reply to,
    and nothing they say can move a belief."""
    # Arrange
    model = ScriptedModel()

    # Act
    await ClaudeTutor("m", client=model).teach(
        _move(), _node(), topic="How neural networks learn", criterion=None, run_id="r1"
    )

    # Assert
    prompt = model.prompts[0].lower()
    assert "end by asking them to do exactly this" not in prompt
    assert "question that makes them think" in prompt


async def test_the_stub_asks_the_staged_criterion_too() -> None:
    """The offline path has to put a real question in front of the learner, or nothing downstream —
    the grader, the belief, the director's next move — can be exercised without a provider."""
    # Arrange
    criterion = MasteryCriterion(
        kind=MasteryCriterionKind.EXPLAIN, statement="Explain the gradient in your own words."
    )

    # Act
    said = await StubTutor().teach(
        _move(), _node(), topic="How neural networks learn", criterion=criterion, run_id="r1"
    )

    # Assert
    assert criterion.statement in said


# ── failing honestly ───────────────────────────────────────────────────────────────────────────


async def test_a_provider_failure_is_a_turn_that_did_not_happen() -> None:
    """Not a turn taught from the definition. A degraded turn would look to the learner model like
    teaching that landed badly, and to a reader of the transcript like a tutor doing a poor job —
    when what actually happened is that nobody taught anything."""

    class Broken:
        async def ainvoke(self, prompt: str) -> AIMessage:
            raise RuntimeError("provider is down")

    # Act / Assert
    with pytest.raises(TutorUnavailableError):
        await _taught(Broken())


async def test_a_blank_response_is_a_failure_rather_than_an_empty_turn() -> None:
    """``SessionTurn.tutor`` is ``min_length=1``: a turn the learner cannot see is a decision that
    happened to them invisibly. Caught here, where it can still be named, rather than as a
    validation error thrown from inside session assembly."""
    # Act / Assert
    with pytest.raises(TutorUnavailableError):
        await _taught(ScriptedModel("   \n  "))


async def test_the_tutor_gives_up_before_the_learner_does() -> None:
    """A learner is watching a cursor blink. A provider call that never returns has to become a
    failure they can retry, not a session that hangs."""

    class Hanging:
        async def ainvoke(self, prompt: str) -> AIMessage:
            await asyncio.sleep(30)
            raise AssertionError("should have been cancelled")

    # Act / Assert
    async with asyncio.timeout(5):
        with pytest.raises(TutorUnavailableError):
            await ClaudeTutor("m", client=Hanging(), deadline_s=0.05).teach(
                _move(), _node(), topic="How neural networks learn", run_id="r1"
            )


# ── the offline tutor ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kind", [MoveKind.INTRODUCE, MoveKind.RETRIEVE, MoveKind.REMEDIATE], ids=lambda k: k.value
)
async def test_the_stub_teaches_the_concept_it_was_given(kind: MoveKind) -> None:
    """The offline path is what CI and keyless dev run, so the stub has to be a real implementation
    of the contract rather than lorem: text that named no concept would let the whole session be
    wired to the wrong node without a single test noticing."""
    # Act
    taught = await StubTutor().teach(
        _move(kind), _node(), topic="How neural networks learn", run_id="r1"
    )

    # Assert
    assert "Gradient" in taught


async def test_the_stub_says_something_different_for_each_move() -> None:
    """Same reason the real tutor does: a surface built against a stub that ignored the move would
    look finished while showing the learner one thing forever."""
    # Act
    said = {
        kind: await StubTutor().teach(
            _move(kind), _node(), topic="How neural networks learn", run_id="r1"
        )
        for kind in (MoveKind.INTRODUCE, MoveKind.RETRIEVE, MoveKind.REMEDIATE)
    }

    # Assert
    assert len(set(said.values())) == 3


async def test_the_stub_surfaces_the_misconception_too() -> None:
    """So the offline path exercises the same claim the keyed one does — the API-level test that
    proves a node's authored notes reach the learner runs on this tutor."""
    # Act
    taught = await StubTutor().teach(
        _move(), _node(), topic="How neural networks learn", run_id="r1"
    )

    # Assert
    assert _MISCONCEPTION in taught


async def test_the_stub_refuses_a_close_the_same_way_the_real_tutor_does() -> None:
    """Both tutors have to agree on what a tutor is for, or the offline path would prove a contract
    production does not hold. ``open_session`` filters CLOSE out before either of them sees it, so
    this is the only place the rule is visible — untested, it becomes dead code at the next
    refactor, and the first caller to reach it directly gets an ``AttributeError`` on ``None``."""
    # Act / Assert
    with pytest.raises(ValueError):
        await StubTutor().teach(
            DirectorMove(kind=MoveKind.CLOSE, reason="Time is up."),
            _node(),
            topic="How neural networks learn",
            run_id="r1",
        )


async def test_the_stub_teaches_a_concept_with_no_notes_at_all() -> None:
    # Arrange
    bare = ConceptNode(id="gradient", name="Gradient", definition="The slope of the loss.")

    # Act
    taught = await StubTutor().teach(_move(), bare, topic="How neural networks learn", run_id="r1")

    # Assert
    assert taught.strip()
    assert "Gradient" in taught
