"""The grader: turning a free-text answer into evidence (Phase 2a, T5).

U1 is the decision this file exists to hold: the tutor stages one of the concept's do-statements,
the learner answers in prose, and a *separate* grader scores that answer against that criterion.
Rejected alternatives were the tutor reporting its own confidence (the teacher marking its own
homework, with the learner model then built on that bias) and learner self-rating (poorly correlated
with mastery, and it makes the learner do the system's job).

Three verdicts and not a score: the grader is judging one answer against one explicit do-statement,
and asking it for 0.73 would be asking for a precision it does not have.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from lunaris_live.graph import ConceptNode, MasteryCriterion, MasteryCriterionKind
from lunaris_live.session import (
    ClaudeGrader,
    EvidenceKind,
    GraderUnavailableError,
    StubGrader,
)

_CRITERION = MasteryCriterion(
    kind=MasteryCriterionKind.PREDICT,
    statement="Say which way a weight should move to lower the loss.",
)

_NODE = ConceptNode(
    id="gradient",
    name="Gradient",
    definition="How much the loss changes for a small change in each weight.",
)


class ScriptedModel:
    """Replays one response and records the prompts it was asked with."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content=self._reply)


async def _graded(model: object, answer: str = "Downhill, opposite the gradient."):
    return await ClaudeGrader("m", client=model).grade(
        answer, criterion=_CRITERION, node=_NODE, run_id="r1"
    )


# ── what the grader is judging ─────────────────────────────────────────────────────────────────


async def test_the_answer_is_judged_against_the_staged_criterion() -> None:
    """Not against the concept in general. A grader marking "did they say something sensible about
    gradients" would pass an answer that never did the thing the learner was asked to do, and the
    learner model would then record mastery of a criterion nobody checked."""
    # Arrange
    model = ScriptedModel('{"verdict": "met", "reason": "Named the descent direction."}')

    # Act
    await _graded(model)

    # Assert — the do-statement itself, verbatim, plus the answer being judged.
    prompt = model.prompts[0]
    assert _CRITERION.statement in prompt
    assert "Downhill, opposite the gradient." in prompt


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ("met", EvidenceKind.MET),
        ("partial", EvidenceKind.PARTIAL),
        ("not_met", EvidenceKind.NOT_MET),
    ],
)
async def test_every_verdict_the_grader_may_return_is_understood(
    verdict: str, expected: EvidenceKind
) -> None:
    # Arrange
    model = ScriptedModel(f'{{"verdict": "{verdict}", "reason": "Because."}}')

    # Act
    grade = await _graded(model)

    # Assert
    assert grade.kind is expected


async def test_the_grade_carries_the_reasoning_that_produced_it() -> None:
    """A learner is told they have not met a bar; "why" is the difference between feedback and a
    verdict. It is also the only way to audit a grader that is quietly wrong."""
    # Arrange
    model = ScriptedModel('{"verdict": "partial", "reason": "Right direction, no magnitude."}')

    # Act
    grade = await _graded(model)

    # Assert
    assert grade.reason == "Right direction, no magnitude."


# ── failing honestly ───────────────────────────────────────────────────────────────────────────


async def test_an_unrecognised_verdict_is_not_guessed_at() -> None:
    """Coercing "mostly" to MET would move a learner's belief on the strength of a word nobody
    defined — and the director gates introductions on that belief."""
    # Arrange
    model = ScriptedModel('{"verdict": "mostly", "reason": "Close enough."}')

    # Act / Assert
    with pytest.raises(GraderUnavailableError):
        await _graded(model)


async def test_an_unparseable_response_is_not_evidence() -> None:
    # Act / Assert
    with pytest.raises(GraderUnavailableError):
        await _graded(ScriptedModel("I think they did fine, honestly."))


async def test_a_provider_failure_is_not_evidence_either() -> None:
    """Silence must never read as a wrong answer. Defaulting a failed grade to NOT_MET would have
    an outage teach the system that the learner does not understand the concept."""

    class Broken:
        async def ainvoke(self, prompt: str) -> AIMessage:
            raise RuntimeError("provider is down")

    # Act / Assert
    with pytest.raises(GraderUnavailableError):
        await _graded(Broken())


async def test_the_grader_gives_up_before_the_learner_does() -> None:
    """Grading is one classification of one answer; a learner is waiting on it to find out whether
    they were right, so a hung call has to become a failure they can retry."""

    class Hanging:
        async def ainvoke(self, prompt: str) -> AIMessage:
            await asyncio.sleep(30)
            raise AssertionError("should have been cancelled")

    # Act / Assert
    async with asyncio.timeout(5):
        with pytest.raises(GraderUnavailableError):
            await ClaudeGrader("m", client=Hanging(), deadline_s=0.05).grade(
                "Downhill.", criterion=_CRITERION, node=_NODE, run_id="r1"
            )


# ── the offline grader ─────────────────────────────────────────────────────────────────────────


async def test_the_stub_can_reach_every_verdict() -> None:
    """The offline path has to be able to drive the loop BOTH ways — a stub that always passed
    would leave remediation, the whole reason the director has a stuck rule, permanently untested
    below the API."""
    # Act
    strong = await StubGrader().grade(
        "The weight should move which way lowers the loss, opposite the gradient.",
        criterion=_CRITERION,
        node=_NODE,
        run_id="r1",
    )
    partial = await StubGrader().grade(
        "The loss should go down.", criterion=_CRITERION, node=_NODE, run_id="r1"
    )
    missed = await StubGrader().grade(
        "No idea, sorry.", criterion=_CRITERION, node=_NODE, run_id="r1"
    )

    # Assert
    assert (strong.kind, partial.kind, missed.kind) == (
        EvidenceKind.MET,
        EvidenceKind.PARTIAL,
        EvidenceKind.NOT_MET,
    )


async def test_the_stub_says_why_as_well() -> None:
    """Same contract as the real one, or a surface built against the stub would have an empty
    feedback line the keyed path then fills — and nobody would have designed for it."""
    # Act
    grade = await StubGrader().grade(
        "No idea, sorry.", criterion=_CRITERION, node=_NODE, run_id="r1"
    )

    # Assert
    assert grade.reason.strip()


async def test_an_empty_answer_is_not_a_pass() -> None:
    # Act
    grade = await StubGrader().grade("   ", criterion=_CRITERION, node=_NODE, run_id="r1")

    # Assert
    assert grade.kind is EvidenceKind.NOT_MET
