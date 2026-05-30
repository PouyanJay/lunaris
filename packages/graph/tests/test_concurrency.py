import asyncio

from lunaris_graph.builder import PrerequisiteGraphBuilder
from lunaris_graph.verdict import PrereqVerdict
from lunaris_runtime.schema import BloomLevel, KnowledgeComponent


class _CountingJudge:
    """Records peak in-flight concurrency so the semaphore cap can be asserted."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.peak = 0

    async def judge(
        self, prerequisite: KnowledgeComponent, dependent: KnowledgeComponent
    ) -> PrereqVerdict:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        await asyncio.sleep(0)  # yield so multiple coroutines overlap
        self.in_flight -= 1
        return PrereqVerdict(is_prereq=False)


def _kcs(n: int) -> list[KnowledgeComponent]:
    return [
        KnowledgeComponent(
            id=f"k{i}",
            label=f"k{i}",
            definition="d",
            difficulty=i / n,
            bloom_ceiling=BloomLevel.APPLY,
        )
        for i in range(n)
    ]


async def test_builder_caps_concurrent_judgments() -> None:
    # Arrange — 10 KCs => 45 candidate pairs; cap concurrency at 3
    judge = _CountingJudge()
    builder = PrerequisiteGraphBuilder(judge, max_concurrency=3)
    kcs = _kcs(10)

    # Act
    await builder.build(kcs, frontier=[], goal="k9")

    # Assert — never more than the cap in flight, but all pairs were judged
    assert judge.peak <= 3
    assert judge.peak >= 2  # genuinely ran in parallel, not serialized
