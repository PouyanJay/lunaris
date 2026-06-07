from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchBudget:
    """A hard per-build cap on research cost (P7.2): how many searches + page fetches are allowed.

    Research is always-on, so it must be bounded — these caps stop an always-on step from running
    away (decision §12.6). ``max_searches`` and ``max_fetches`` are TOTAL caps across the whole
    research (the cost ceiling, spent down across rounds — ``max_fetches`` counts fetch *attempts*,
    so a page that fails to extract still costs its slot); ``max_rounds`` bounds the adaptive
    deepening loop (CQ Phase 1.1): each round searches, fetches, distils a structured framework, and
    may propose follow-up queries for thin areas — the loop deepens until coverage is met, the round
    ceiling is hit, or the search/fetch budget runs out. Exhaustion degrades honestly (fewer or no
    sources → PARTIAL/UNAVAILABLE) rather than blocking the build. Defaults match a few narrow
    searches over up to two rounds; CQ Phase 1.2 sizes them to the goal.
    """

    max_searches: int = 3
    max_fetches: int = 4
    max_rounds: int = 2

    def __post_init__(self) -> None:
        # A negative cap slices silently wrong (``queries[:-1]`` keeps all but one); reject it.
        if self.max_searches < 0 or self.max_fetches < 0:
            raise ValueError("research budget caps must be non-negative")
        if self.max_rounds < 1:
            raise ValueError("research budget must allow at least one round")
