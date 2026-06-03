from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceBudget:
    """A per-lesson cap on resource-curation cost (P7.4): searches issued + resources attached.

    Curation is best-effort and runs per lesson, so it must be bounded — these caps stop it from
    issuing unbounded searches or flooding a lesson with links. The curator runs at most
    ``max_searches`` queries and attaches at most ``max_resources`` vetted resources to a lesson;
    exhaustion degrades honestly (fewer or no resources) rather than blocking the build. Aggregate
    per-build cost is naturally bounded by the (small) module count times these caps.
    """

    max_searches: int = 4
    max_resources: int = 4

    def __post_init__(self) -> None:
        if self.max_searches < 0 or self.max_resources < 0:
            raise ValueError("resource budget caps must be non-negative")
