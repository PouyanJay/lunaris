"""The per-build cost bound for discovery (the searches + fetches are the paid calls)."""

from dataclasses import dataclass

from lunaris_runtime.schema import DiscoveryDepth


@dataclass(frozen=True)
class DiscoveryBudget:
    """Caps a discovery run: how much each reflect round may spend, and how many rounds may run.

    Searches and fetches are the paid calls, so they are bounded *per round*; ``max_rounds`` bounds
    the reflect cycle (like the authoring loop's revise cap), so the worst case is a small, knowable
    multiple. The defaults are moderate — enough to ground a real curriculum, low enough that a
    build can't run away. (A soft cap that asks the human before exceeding it is the intended next
    step.)
    """

    searches_per_round: int = 6
    fetches_per_round: int = 8
    max_rounds: int = 2

    def __post_init__(self) -> None:
        if self.searches_per_round < 0:
            raise ValueError("searches_per_round must be non-negative")
        if self.fetches_per_round < 0:
            raise ValueError("fetches_per_round must be non-negative")
        if self.max_rounds < 1:
            raise ValueError("max_rounds must allow at least one round")


# THOROUGH is the STANDARD budget with its width doubled and one extra reflect round — so it
# corroborates more concepts across more domains for a higher search cost (the pre-authorized "go
# deeper" the learner opts into when STANDARD leaves concepts thin). Derived from the STANDARD
# defaults so the doubled-width / one-extra-round relationship survives a retune of those defaults.
_STANDARD_BUDGET = DiscoveryBudget()
_THOROUGH_BUDGET = DiscoveryBudget(
    searches_per_round=_STANDARD_BUDGET.searches_per_round * 2,
    fetches_per_round=_STANDARD_BUDGET.fetches_per_round * 2,
    max_rounds=_STANDARD_BUDGET.max_rounds + 1,
)


def budget_for_depth(depth: DiscoveryDepth) -> DiscoveryBudget:
    """The per-build budget for a chosen discovery depth (STANDARD = the moderate default)."""
    return _THOROUGH_BUDGET if depth == DiscoveryDepth.THOROUGH else _STANDARD_BUDGET
