"""Hand-built golden prerequisite graphs (build-spec §10).

Each domain is a set of KCs + the minimal (transitively-reduced) prerequisite edges
a human expert would draw + the goal. Used by both the deterministic assembly tests
and the live-LLM eval.
"""

from dataclasses import dataclass

from lunaris_runtime.schema import BloomLevel, KnowledgeComponent


@dataclass(frozen=True)
class GoldenDomain:
    name: str
    kcs: list[KnowledgeComponent]
    edges: list[tuple[str, str]]  # minimal prerequisite edges (from -> to)
    goal: str


def _kc(kc_id: str, label: str, difficulty: float, definition: str = "") -> KnowledgeComponent:
    return KnowledgeComponent(
        id=kc_id,
        label=label,
        definition=definition or label,
        difficulty=difficulty,
        bloom_ceiling=BloomLevel.APPLY,
    )


BINARY_SEARCH = GoldenDomain(
    name="binary_search",
    kcs=[
        _kc(
            "comparison",
            "Comparing values",
            0.1,
            "Determining whether one value is <, =, or > another.",
        ),
        _kc(
            "arrays",
            "Arrays / indexed lists",
            0.2,
            "Contiguous, index-addressable sequences of elements.",
        ),
        _kc(
            "loops", "Loops and iteration", 0.3, "Repeating a block of code, e.g. while/for loops."
        ),
        _kc(
            "sorted_order",
            "Sorted order",
            0.45,
            "An ordering invariant where elements are non-decreasing.",
        ),
        _kc(
            "binary_search",
            "Binary search",
            0.75,
            "Halving a sorted range repeatedly to locate a target in O(log n).",
        ),
    ],
    edges=[
        ("arrays", "binary_search"),
        ("loops", "binary_search"),
        ("sorted_order", "binary_search"),
        ("comparison", "sorted_order"),
    ],
    goal="binary_search",
)


ALL_DOMAINS = [BINARY_SEARCH]
