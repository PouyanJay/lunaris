from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchBudget:
    """A hard per-build cap on research cost (P7.2): how many searches + page fetches are allowed.

    Research is always-on, so it must be bounded — these caps stop an always-on step from running
    away (decision §12.6). The researcher issues at most ``max_searches`` queries and fetches at
    most ``max_fetches`` of the highest-trust candidates; exhaustion degrades honestly (fewer or no
    sources → PARTIAL/UNAVAILABLE) rather than blocking the build. Defaults match a few narrow
    searches.
    """

    max_searches: int = 3
    max_fetches: int = 4

    def __post_init__(self) -> None:
        # A negative cap slices silently wrong (``queries[:-1]`` keeps all but one); reject it.
        if self.max_searches < 0 or self.max_fetches < 0:
            raise ValueError("research budget caps must be non-negative")
