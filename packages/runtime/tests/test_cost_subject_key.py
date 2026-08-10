"""What a cost row is *about* — the ledger's rollup key (D2).

Costs used to be keyed by ``course_id``, because a course was the only thing that could spend money.
Lunaris Live's concept graphs spend too, and a graph is not a course: it has its own id space, its
own lifecycle, and its own purge. Keying both by a column called ``course_id`` would mean two
different kinds of thing sharing one namespace by accident — so a cost is now keyed by *what it was
spent on*: ``(subject_type, subject_id)``.

The ledger is append-only financial data, which is why this lands now rather than when Live's
metering does: re-keying rows nobody may rewrite is the expensive kind of migration.
"""

import pytest
from lunaris_runtime.metering import CostScope, cost_scope, drain_cost_scope, record_cost
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemorySubjectCostStore
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostProvider, CostSubjectType, CostUnit


def _price_of(tokens: float) -> float:
    """What the live price book charges for ``tokens`` input tokens on the model used here.

    Read from the book rather than hardcoded, so a rate change does not turn these into false
    failures — and so the assertions stay about the *key*, not about a number."""
    return PriceBook.current().cost(
        provider=CostProvider.ANTHROPIC,
        model="claude-opus-4-8",
        unit=CostUnit.INPUT_TOKENS,
        count=tokens,
    )


async def _spend(
    ledger: InMemoryCostEventStore,
    rollup: InMemorySubjectCostStore,
    *,
    subject_type: CostSubjectType,
    subject_id: str,
    run_id: str,
    tokens: float,
) -> None:
    """Drive one metered call through a real scope and drain it, as a build boundary does."""
    scope = CostScope(
        run_id=run_id,
        subject_type=subject_type,
        subject_id=subject_id,
        price_book=PriceBook.current(),
    )
    with cost_scope(scope):
        record_cost(
            component="compile",
            provider=CostProvider.ANTHROPIC,
            model="claude-opus-4-8",
            usage={CostUnit.INPUT_TOKENS: tokens},
        )
    await drain_cost_scope(scope, ledger, rollup)


async def test_a_course_and_a_graph_that_share_an_id_are_two_different_subjects() -> None:
    """The whole point of the composite key.

    Course ids and graph ids are minted from different sequences, so nothing stops them colliding.
    Under the old single-column key that collision silently merged one product's spend into the
    other's total — money attributed to the wrong thing, in an append-only ledger nobody may
    correct afterwards.
    """
    # Arrange
    ledger, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()

    # Act — same id, different kinds of subject.
    await _spend(
        ledger,
        rollup,
        subject_type=CostSubjectType.COURSE,
        subject_id="shared-id",
        run_id="r-course",
        tokens=1000,
    )
    await _spend(
        ledger,
        rollup,
        subject_type=CostSubjectType.LIVE_GRAPH,
        subject_id="shared-id",
        run_id="r-graph",
        tokens=3000,
    )

    # Assert — two rollups, neither carrying the other's spend.
    course = await rollup.get(subject_type=CostSubjectType.COURSE, subject_id="shared-id")
    graph = await rollup.get(subject_type=CostSubjectType.LIVE_GRAPH, subject_id="shared-id")
    assert course is not None and graph is not None
    # Two distinct rollups, each counting one call. Asserted absolutely rather than as a ratio
    # between them: a store that collapsed both subjects into one namespace returns the SAME object
    # twice, with a total recomputed from a mis-scoped (empty) ledger — and `0 == 0 * 3` holds.
    # A relative assertion is satisfied by exactly the failure this test exists to catch.
    assert course is not graph
    assert course.breakdown["eventCount"] == 1
    assert graph.breakdown["eventCount"] == 1
    expected_course = _price_of(1000)
    assert course.total_amount == pytest.approx(expected_course)
    assert graph.total_amount == pytest.approx(_price_of(3000))
    assert expected_course > 0, "a zero price book would make every assertion here vacuous"


async def test_the_ledger_reads_back_by_subject_not_by_bare_id() -> None:
    # Arrange
    ledger, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    await _spend(
        ledger,
        rollup,
        subject_type=CostSubjectType.COURSE,
        subject_id="shared-id",
        run_id="r-course",
        tokens=1000,
    )
    await _spend(
        ledger,
        rollup,
        subject_type=CostSubjectType.LIVE_GRAPH,
        subject_id="shared-id",
        run_id="r-graph",
        tokens=3000,
    )

    # Act
    events = await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id="shared-id"
    )

    # Assert — the drill-through shows one subject's spend, and says what it was spent on.
    assert [event.run_id for event in events] == ["r-graph"]
    assert events[0].subject_type is CostSubjectType.LIVE_GRAPH
    assert events[0].subject_id == "shared-id"


async def test_purging_one_subject_leaves_the_other_intact() -> None:
    """Purge is the other half of the key: deleting a course must not take a graph's ledger with
    it. Under a shared id namespace it would have — silently, and unrecoverably."""
    # Arrange
    ledger, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    for subject_type, run_id in (
        (CostSubjectType.COURSE, "r-course"),
        (CostSubjectType.LIVE_GRAPH, "r-graph"),
    ):
        await _spend(
            ledger,
            rollup,
            subject_type=subject_type,
            subject_id="shared-id",
            run_id=run_id,
            tokens=1000,
        )

    # Act
    await ledger.delete_for_subject(subject_type=CostSubjectType.COURSE, subject_id="shared-id")
    await rollup.delete_for_subject(subject_type=CostSubjectType.COURSE, subject_id="shared-id")

    # Assert
    assert (
        await ledger.list_for_subject(subject_type=CostSubjectType.COURSE, subject_id="shared-id")
        == []
    )
    assert (await rollup.get(subject_type=CostSubjectType.COURSE, subject_id="shared-id")) is None
    assert await ledger.list_for_subject(
        subject_type=CostSubjectType.LIVE_GRAPH, subject_id="shared-id"
    )
    assert (
        await rollup.get(subject_type=CostSubjectType.LIVE_GRAPH, subject_id="shared-id")
    ) is not None
