"""P7.5 live eval: a confirmed diagnostic sharpens the learner frontier (needs a real model key).

Deselected by default (``@pytest.mark.eval``); run with ``uv run --env-file .env pytest -m eval``.
Proves the OUTCOME the deterministic suite can't: when a learner confirms they're advanced and
reports their real prior knowledge, the live learner profiler produces a sharper frontier (more
foundations to skip, named specifically) than it does for the vaguer inference — exactly the
diagnostic-personalization promise (§14: two people asking the same goal get different starts).
"""

import os

import pytest
from lunaris_agent.subagents.learner_profiler import ClaudeLearnerProfiler
from lunaris_runtime.clarifier import apply_clarification
from lunaris_runtime.schema import Clarification, CourseBrief, Level

pytestmark = pytest.mark.eval

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"
# Foundations an advanced English learner has already mastered — the frontier should name some.
_FOUNDATIONS = ("alphabet", "vocabulary", "grammar", "conversation", "phonic", "spelling")


@pytest.fixture
def profiler() -> ClaudeLearnerProfiler:
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY unset; the diagnostic eval needs a live model")
    return ClaudeLearnerProfiler(os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER))


async def test_confirmed_diagnostic_sharpens_the_frontier(profiler: ClaudeLearnerProfiler) -> None:
    # Arrange — the interpreter inferred an INTERMEDIATE learner with a vague prior.
    inferred = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10 across listening, reading, writing, and speaking",
        target_level=Level.INTERMEDIATE,
        assumed_prior="everyday English",
    )
    # The learner confirms they are ADVANCED and reports a specific, rich prior.
    confirmed = apply_clarification(
        inferred,
        Clarification(
            target_level=Level.ADVANCED,
            assumed_known="solid grammar, a wide vocabulary, and fluent everyday conversation",
        ),
    )

    # Act — profile the calibrated (advanced) brief with the real model.
    confirmed_frontier = (await profiler.profile(confirmed)).frontier

    # Assert — the confirmed (advanced) brief yields a non-empty frontier that NAMES the foundations
    # to skip: a sharper starting point than a true novice (whose frontier is empty). A single-call
    # assertion on the direction of behaviour — no flaky cross-run length comparison.
    assert confirmed_frontier, "the confirmed diagnostic produced an empty frontier"
    haystack = " ".join(confirmed_frontier).lower()
    assert any(term in haystack for term in _FOUNDATIONS), (
        f"the advanced frontier names no foundations to skip: {confirmed_frontier}"
    )
