"""Size the discovery budget to the curriculum (CQ Phase 1.4)."""

from lunaris_runtime.schema import DiscoveryDepth

from .budget import DiscoveryBudget, budget_for_depth

# Hard per-round ceiling: a very large curriculum must not make discovery run away on cost.
_MAX_PER_ROUND = 24


def _clamp(value: int, floor: int, ceiling: int) -> int:
    return min(max(value, floor), ceiling)


def discovery_budget_for(depth: DiscoveryDepth, kc_count: int) -> DiscoveryBudget:
    """Size discovery to the curriculum: every KC gets at least one query + one fetch per round.

    The depth (STANDARD/THOROUGH) sets the floor and the reflect-round count; the per-round width is
    raised to cover all KCs (clamped to ``_MAX_PER_ROUND``), so no concept is left unsearched by a
    fixed-width floor — the live CLB diagnosis was discovery deep for only 1 of 8 KCs because a
    width of 6 left most concepts unqueried. Never narrower than the depth floor.
    """
    base = budget_for_depth(depth)
    return DiscoveryBudget(
        searches_per_round=_clamp(kc_count, base.searches_per_round, _MAX_PER_ROUND),
        fetches_per_round=_clamp(kc_count, base.fetches_per_round, _MAX_PER_ROUND),
        max_rounds=base.max_rounds,
    )
