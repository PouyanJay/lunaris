"""Integration tests for the cost metering seam (course-cost-metering, T3).

They traverse the real metering vertical: ``record_cost`` (the call every paid seam makes) ->
``PriceBook`` (calculated amount) -> ``credential_pocket`` (BYOK vs platform, off the real
credential scope) -> the scope buffer -> ``drain_cost_scope`` -> ``CostEventRecorder`` -> the
append-only ledger and the ``course_costs`` rollup. No stubs on the system under test; only the
store is an in-memory fake. Deep seams calling ``record_cost`` for each provider come in T4-T7; here
the call is exercised directly to prove the seam prices, attributes, and persists correctly.
"""

import pytest
from lunaris_api.cost_drain import drain_cost_scope
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.metering import CostScope, cost_scope, current_cost_scope, record_cost
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemoryCourseCostStore
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostPocket, CostProvider, CostUnit

_RUN_ID = "run-seam"
_COURSE_ID = "course-seam"
_OPUS = "claude-opus-4-8"  # $5/MTok in, $25/MTok out


def _scope() -> CostScope:
    return CostScope(run_id=_RUN_ID, course_id=_COURSE_ID, price_book=PriceBook.current())


async def test_record_cost_prices_and_persists_a_claude_call() -> None:
    # Arrange
    event_store, cost_store = InMemoryCostEventStore(), InMemoryCourseCostStore()
    scope = _scope()

    # Act — a "deep" Claude call records 1M input + 1M output tokens inside the run's cost scope.
    with cost_scope(scope):
        record_cost(
            component="module_author",
            provider=CostProvider.ANTHROPIC,
            model=_OPUS,
            usage={CostUnit.INPUT_TOKENS: 1_000_000, CostUnit.OUTPUT_TOKENS: 1_000_000},
        )
    await drain_cost_scope(scope, event_store, cost_store)

    # Assert — calculated cost = $5 (input) + $25 (output) = $30, persisted to ledger + rollup.
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    assert rollup.total_amount == pytest.approx(30.0)
    assert rollup.breakdown["byProvider"]["anthropic"] == pytest.approx(30.0)
    assert rollup.breakdown["byComponent"]["module_author"] == pytest.approx(30.0)
    ledger = await event_store.list_for_course(course_id=_COURSE_ID)
    assert [e.component for e in ledger] == ["module_author"]
    # usage keys are CostUnit values (the auditable measured units the cost was calculated from).
    assert ledger[0].usage == {"input_tokens": 1_000_000, "output_tokens": 1_000_000}


async def test_cache_tokens_price_at_the_split_rates() -> None:
    # Cache read is 0.1x input and cache write is 1.25x input, so metering them separately matters.
    event_store, cost_store = InMemoryCostEventStore(), InMemoryCourseCostStore()
    scope = _scope()
    with cost_scope(scope):
        record_cost(
            component="planner",
            provider=CostProvider.ANTHROPIC,
            model=_OPUS,
            usage={
                CostUnit.CACHE_READ_TOKENS: 1_000_000,  # 0.1 x $5 = $0.50
                CostUnit.CACHE_WRITE_TOKENS: 1_000_000,  # 1.25 x $5 = $6.25
            },
        )
    await drain_cost_scope(scope, event_store, cost_store)
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    assert rollup.total_amount == pytest.approx(0.50 + 6.25)


async def test_user_key_pocket_persists_through_ledger_and_rollup() -> None:
    # Arrange — a build on the tenant's own Anthropic key.
    event_store, cost_store = InMemoryCostEventStore(), InMemoryCourseCostStore()
    scope = _scope()

    # Act
    with run_credentials({"ANTHROPIC_API_KEY": "sk-tenant-test"}), cost_scope(scope):
        record_cost(
            component="planner",
            provider=CostProvider.ANTHROPIC,
            model=_OPUS,
            usage={CostUnit.INPUT_TOKENS: 1_000_000},  # $5
        )
    await drain_cost_scope(scope, event_store, cost_store)

    # Assert — the user_key pocket survives to the ledger row AND the rollup's byPocket split.
    ledger = await event_store.list_for_course(course_id=_COURSE_ID)
    assert ledger[0].pocket is CostPocket.USER_KEY
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    assert rollup.breakdown["byPocket"]["user_key"] == pytest.approx(5.0)
    assert rollup.breakdown["byPocket"]["platform"] == pytest.approx(0.0)


async def test_platform_pocket_persists_through_ledger_and_rollup() -> None:
    # Arrange — no credential scope carrying the key → platform (env / infra) spend.
    event_store, cost_store = InMemoryCostEventStore(), InMemoryCourseCostStore()
    scope = _scope()

    # Act
    with cost_scope(scope):
        record_cost(
            component="planner",
            provider=CostProvider.ANTHROPIC,
            model=_OPUS,
            usage={CostUnit.INPUT_TOKENS: 1_000_000},  # $5
        )
    await drain_cost_scope(scope, event_store, cost_store)

    # Assert — the platform pocket lands on the ledger row and the rollup split.
    ledger = await event_store.list_for_course(course_id=_COURSE_ID)
    assert ledger[0].pocket is CostPocket.PLATFORM
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    assert rollup.breakdown["byPocket"]["platform"] == pytest.approx(5.0)
    assert rollup.breakdown["byPocket"]["user_key"] == pytest.approx(0.0)


async def test_render_compute_bills_to_platform_even_under_a_tenant_scope() -> None:
    # Arrange — render compute has no BYOK key, so it's platform spend even when a DIFFERENT
    # provider's tenant key is live in the same scope (guards against "any active key -> user_key").
    event_store, cost_store = InMemoryCostEventStore(), InMemoryCourseCostStore()
    scope = _scope()

    # Act
    with run_credentials({"ANTHROPIC_API_KEY": "sk-tenant"}), cost_scope(scope):
        record_cost(
            component="render",
            provider=CostProvider.MANIM,
            model=None,
            usage={CostUnit.COMPUTE_SECONDS: 120},
        )
    await drain_cost_scope(scope, event_store, cost_store)

    # Assert
    ledger = await event_store.list_for_course(course_id=_COURSE_ID)
    assert ledger[0].pocket is CostPocket.PLATFORM
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    assert rollup.breakdown["byPocket"]["platform"] == pytest.approx(120 * 0.0000024)
    assert rollup.breakdown["byPocket"]["user_key"] == pytest.approx(0.0)


async def test_record_cost_degrades_to_zero_on_an_unpriced_unit() -> None:
    # Arrange — a mixed call: a priced unit plus a unit with no rate for this provider (Anthropic
    # has no IMAGES rate). The un-priced unit must degrade to 0, not crash the build.
    event_store, cost_store = InMemoryCostEventStore(), InMemoryCourseCostStore()
    scope = _scope()

    # Act
    with cost_scope(scope):
        record_cost(
            component="planner",
            provider=CostProvider.ANTHROPIC,
            model=_OPUS,
            usage={CostUnit.INPUT_TOKENS: 1_000_000, CostUnit.IMAGES: 3},
        )
    await drain_cost_scope(scope, event_store, cost_store)

    # Assert — amount reflects only the priced portion ($5); both units are still recorded
    # (auditable), the un-priced one just contributed 0. No exception raised.
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    assert rollup.total_amount == pytest.approx(5.0)
    ledger = await event_store.list_for_course(course_id=_COURSE_ID)
    assert ledger[0].usage == {"input_tokens": 1_000_000, "images": 3}


async def test_record_cost_is_a_noop_without_a_scope() -> None:
    # Outside a build (admin/eval/CLI/tests) metering turns itself off — no scope, no crash.
    assert current_cost_scope() is None
    record_cost(
        component="planner",
        provider=CostProvider.ANTHROPIC,
        model=_OPUS,
        usage={CostUnit.INPUT_TOKENS: 100},
    )  # must not raise
    assert current_cost_scope() is None  # nothing entered a scope as a side effect


async def test_keyless_local_call_records_zero_cost() -> None:
    # A keyless build's local fallback is metered but prices to $0 — an honest "~$0", not "no data".
    event_store, cost_store = InMemoryCostEventStore(), InMemoryCourseCostStore()
    scope = _scope()
    with cost_scope(scope):
        record_cost(
            component="module_author",
            provider=CostProvider.LOCAL,
            model=None,
            usage={CostUnit.INPUT_TOKENS: 5_000, CostUnit.OUTPUT_TOKENS: 2_000},
        )
    await drain_cost_scope(scope, event_store, cost_store)
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    assert rollup.total_amount == pytest.approx(0.0)
    assert rollup.breakdown["eventCount"] == 1  # metered, not dropped
