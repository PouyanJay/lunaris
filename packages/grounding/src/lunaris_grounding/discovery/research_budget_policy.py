from lunaris_runtime.schema import CourseBrief, GapMagnitude, GoalType, Level

from .research_budget import ResearchBudget

# How much each brief signal raises research depth (CQ Phase 1.2). Keyed off the goal's NATURE, not
# its topic (the Genericity Rule): a goal that must be *done* or *passed* against a real external
# bar, at a high level, across a wide gap, earns more grounding than a casual knowledge intro.
# (domain_field is a free-text tag with no bounded vocabulary, so it carries no depth weight here —
# the three bounded enums hold the signal; see AD6.)
_GOAL_TYPE_DEPTH: dict[GoalType, int] = {
    GoalType.KNOWLEDGE: 0,
    GoalType.BEHAVIOR: 1,
    GoalType.SKILL: 2,
    GoalType.CREDENTIAL: 2,
}
_LEVEL_DEPTH: dict[Level, int] = {
    Level.NOVICE: 0,
    Level.NOT_APPLICABLE: 0,
    Level.INTERMEDIATE: 0,
    Level.ADVANCED: 1,
    Level.EXPERT: 1,
}
_GAP_DEPTH: dict[GapMagnitude, int] = {
    GapMagnitude.SMALL: 0,
    GapMagnitude.MODERATE: 1,
    GapMagnitude.LARGE: 2,
}

# Depth scores at which the loop earns another round (depth runs 0..5 across the three tables).
_SECOND_ROUND_DEPTH = 2  # depth ≥ this earns a follow-up round
_THIRD_ROUND_DEPTH = 4  # depth ≥ this earns a third deep-dive round


def research_budget_for_brief(brief: CourseBrief) -> ResearchBudget:
    """Size the research budget to the brief (CQ Phase 1.2): scale searches/fetches/rounds by the
    goal's type, target level, and the gap's magnitude.

    Replaces the one-size-fits-all ``ResearchBudget(3, 4)``: a credential/skill goal at the ceiling
    with a large gap (e.g. a from-scratch exam climb) earns deeper, multi-round research than a
    casual knowledge intro, so the always-on step spends where grounding actually matters. The named
    external standard already biases the queries; this sizes how hard the loop digs. Bounded so even
    the deepest brief stays a few rounds of narrow search, never an open-ended crawl.
    """
    depth = (
        _GOAL_TYPE_DEPTH.get(brief.goal_type, 0)
        + _LEVEL_DEPTH.get(brief.target_level, 0)
        + _GAP_DEPTH.get(brief.gap.magnitude, 0)
    )
    return ResearchBudget(
        max_searches=3 + depth,
        max_fetches=4 + depth,
        max_rounds=1 + (depth >= _SECOND_ROUND_DEPTH) + (depth >= _THIRD_ROUND_DEPTH),
    )
