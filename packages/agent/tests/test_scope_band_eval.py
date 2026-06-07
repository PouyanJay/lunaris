"""CQ Phase 3.1 — the scope-band polish eval (live, key-gated).

The hybrid guarantee: the OPTIONAL Claude wording-polish refines the does/doesn't lines but the
deterministic facts (the effort band, the line counts) survive a REAL model call — for any goal
type (the Genericity Rule). Deselected by default; run with a live Anthropic key via ``-m eval``.
The offline ``test_scope_polisher`` suite proves the reconcile guarantee deterministically with a
fake model; this proves it holds against the live model across goal types, and that the polished
band is still a valid, non-empty band.
"""

import os

import pytest
from lunaris_agent.scope import estimate_scope
from lunaris_agent.subagents.scope_polisher import ClaudeScopePolisher
from lunaris_runtime.schema import (
    Course,
    CourseBrief,
    Gap,
    GapMagnitude,
    GoalType,
    Level,
    Module,
)

pytestmark = pytest.mark.eval

# Worker tier (cheap + fast) — wording polish is a light task, like the other subagent evals.
_DEFAULT_WORKER = "claude-haiku-4-5-20251001"

# All four goal types over unrelated subjects — the polish must preserve the facts regardless of the
# goal kind or topic (the Genericity Rule), exercising the goal-specific framing where it diverges.
_CASES = [
    (GoalType.KNOWLEDGE, "relational database internals"),
    (GoalType.CREDENTIAL, "the AWS Solutions Architect exam"),
    (GoalType.SKILL, "technical writing"),
    (GoalType.BEHAVIOR, "a daily mobility routine"),
]


def _course(goal_type: GoalType = GoalType.KNOWLEDGE) -> Course:
    modules = [Module(id=f"k{i}", title=f"Concept {i}", kcs=[f"k{i}"]) for i in range(5)]
    return Course(id="c", topic="anything", goal_type=goal_type, modules=modules)


@pytest.mark.parametrize(("goal_type", "subject"), _CASES)
async def test_live_polish_preserves_the_facts_across_goal_types(
    goal_type: GoalType, subject: str
) -> None:
    # Arrange — a deterministic band for a real goal, and the live worker-tier polisher.
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY unset; the scope-band polish eval needs a live model")
    brief = CourseBrief(
        subject=subject,
        goal=f"reach {subject}",
        goal_type=goal_type,
        target_level=Level.INTERMEDIATE,
        gap=Gap(magnitude=GapMagnitude.MODERATE),
    )
    deterministic = estimate_scope(_course(goal_type), brief)
    polisher = ClaudeScopePolisher(os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER))

    # Act — run the real model through the reconcile guarantee.
    polished = await polisher.polish(deterministic, brief=brief)

    # Assert — the facts survived the live call: the effort is byte-for-byte the deterministic band,
    # the line counts are unchanged, and no line was blanked. The wording MAY differ (that is the
    # point), but a drifting model can never change a fact.
    assert polished.effort == deterministic.effort
    assert len(polished.delivers) == len(deterministic.delivers)
    assert len(polished.excludes) == len(deterministic.excludes)
    assert all(line.strip() for line in polished.delivers)
    assert all(line.strip() for line in polished.excludes)
