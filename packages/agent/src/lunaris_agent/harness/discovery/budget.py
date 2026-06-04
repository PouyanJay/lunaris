"""The per-build cost bound for discovery (the searches + fetches are the paid calls)."""

from dataclasses import dataclass


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
