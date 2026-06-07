"""P7.2-T2 — the per-build research budget's defaults + its non-negative guard."""

import pytest
from lunaris_grounding import ResearchBudget


def test_research_budget_has_bounded_defaults() -> None:
    budget = ResearchBudget()

    assert budget.max_searches == 3
    assert budget.max_fetches == 4


def test_research_budget_rejects_negative_caps() -> None:
    # A negative cap would slice silently wrong (queries[:-1] keeps all but one) — reject it loudly.
    with pytest.raises(ValueError, match="non-negative"):
        ResearchBudget(max_searches=-1)
    with pytest.raises(ValueError, match="non-negative"):
        ResearchBudget(max_fetches=-1)


def test_research_budget_rejects_zero_rounds() -> None:
    # The adaptive loop must run at least once (CQ Phase 1.1); zero rounds is a silent no-op.
    with pytest.raises(ValueError, match="at least one round"):
        ResearchBudget(max_rounds=0)
