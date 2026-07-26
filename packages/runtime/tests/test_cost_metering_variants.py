"""Variant coverage for the cost-metering path (course-cost-metering, T9 — the final journey task).

Where the earlier tasks each proved one provider seam, this parametrizes the *whole* deep path —
``record_cost`` (pricing + pocket resolution) → ``drain_cost_scope`` → append-only ledger + course
rollup — across **every provider x its unit(s), both pockets (user_key vs platform), and a keyless
(all-``local``, ~$0) build**. Amounts are checked against the live ``PriceBook`` (not hardcoded), so
these stay true when a rate changes; the rollup invariant ``total == sum(ledger)`` is asserted for a
realistic mixed build touching all six paid providers.
"""

from collections.abc import Mapping
from contextlib import nullcontext

import pytest
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.metering import CostScope, cost_scope, drain_cost_scope, record_cost
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemoryCourseCostStore
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostPocket, CostProvider, CostUnit

_COURSE_ID = "c-variants"
_RUN_ID = "r-variants"


def _expected_amount(
    provider: CostProvider, model: str | None, usage: dict[CostUnit, float]
) -> float:
    """The price-book-calculated cost of ``usage`` — the sum of ``count x rate`` over every unit."""
    price_book = PriceBook.current()
    return sum(
        price_book.cost(provider=provider, model=model, unit=unit, count=count)
        for unit, count in usage.items()
    )


async def _record_and_drain(
    calls: list[dict[str, object]],
    *,
    credentials: Mapping[str, str] | None = None,
) -> tuple[InMemoryCostEventStore, InMemoryCourseCostStore]:
    """Drive one build's worth of ``record_cost`` calls through a real cost scope and drain it.

    ``credentials`` (env-var → key) enters the run's credential scope so pocket resolution is
    exercised for real; ``None`` runs without a scope. Returns the ledger + rollup stores.
    """
    event_store = InMemoryCostEventStore()
    cost_store = InMemoryCourseCostStore()
    scope = CostScope(run_id=_RUN_ID, course_id=_COURSE_ID, price_book=PriceBook.current())
    creds = run_credentials(credentials) if credentials is not None else nullcontext()
    with creds, cost_scope(scope):
        for call in calls:
            record_cost(**call)  # type: ignore[arg-type]
    await drain_cost_scope(scope, event_store, cost_store)
    return event_store, cost_store


# Every paid provider x a representative unit set. Opus carries the full four-unit Claude call
# (fresh input, cache-read, cache-write, output) so the cache-split pricing is covered; local → 0.
_PROVIDER_VARIANTS: tuple[tuple[str, CostProvider, str | None, dict[CostUnit, float]], ...] = (
    (
        "claude-opus-four-unit",
        CostProvider.ANTHROPIC,
        "claude-opus-4-8",
        {
            CostUnit.INPUT_TOKENS: 1000,
            CostUnit.CACHE_READ_TOKENS: 500,
            CostUnit.CACHE_WRITE_TOKENS: 200,
            CostUnit.OUTPUT_TOKENS: 300,
        },
    ),
    ("claude-haiku", CostProvider.ANTHROPIC, "claude-haiku-4-5", {CostUnit.INPUT_TOKENS: 2000}),
    ("voyage-embeddings", CostProvider.VOYAGE, "voyage-3.5", {CostUnit.INPUT_TOKENS: 10000}),
    ("tavily-search", CostProvider.TAVILY, None, {CostUnit.SEARCH: 3}),
    ("openai-image", CostProvider.OPENAI, "gpt-image-2", {CostUnit.IMAGES: 1}),
    ("elevenlabs-voice", CostProvider.ELEVENLABS, None, {CostUnit.CHARS: 5000}),
    ("manim-render", CostProvider.MANIM, None, {CostUnit.COMPUTE_SECONDS: 42.0}),
    ("local-keyless", CostProvider.LOCAL, None, {CostUnit.INPUT_TOKENS: 9999}),
)


@pytest.mark.parametrize(
    "provider,model,usage",
    [
        pytest.param(provider, model, usage, id=name)
        for name, provider, model, usage in _PROVIDER_VARIANTS
    ],
)
async def test_each_provider_variant_prices_and_rolls_up(
    provider: CostProvider, model: str | None, usage: dict[CostUnit, float]
) -> None:
    # Act — one metered call for this provider variant, through the real price/drain/rollup path.
    event_store, cost_store = await _record_and_drain(
        [{"component": "stage", "provider": provider, "model": model, "usage": usage}]
    )

    # Assert — the ledger row carries the measured usage and the price-book-calculated amount.
    ledger = await event_store.list_for_course(course_id=_COURSE_ID)
    assert len(ledger) == 1
    event = ledger[0]
    assert event.provider is provider
    assert event.model == model
    assert event.usage == {unit.value: count for unit, count in usage.items()}
    assert event.amount == pytest.approx(_expected_amount(provider, model, usage))

    # ...and the rollup materializes that same amount against the provider.
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    assert rollup.total_amount == pytest.approx(event.amount)
    assert rollup.breakdown["byProvider"][provider.value] == pytest.approx(event.amount)


# The keyed providers and the BYOK env-var each authenticates on — the key whose presence flips the
# pocket to user_key. (manim / local have no key, so they can only ever bill to platform.)
_KEYED_PROVIDERS: tuple[tuple[str, CostProvider, str | None, str, dict[CostUnit, float]], ...] = (
    (
        "anthropic",
        CostProvider.ANTHROPIC,
        "claude-opus-4-8",
        "ANTHROPIC_API_KEY",
        {CostUnit.INPUT_TOKENS: 100},
    ),
    (
        "voyage",
        CostProvider.VOYAGE,
        "voyage-3.5",
        "EMBEDDINGS_API_KEY",
        {CostUnit.INPUT_TOKENS: 100},
    ),
    ("tavily", CostProvider.TAVILY, None, "SEARCH_API_KEY", {CostUnit.SEARCH: 1}),
    ("openai", CostProvider.OPENAI, "gpt-image-2", "OPENAI_API_KEY", {CostUnit.IMAGES: 1}),
    ("elevenlabs", CostProvider.ELEVENLABS, None, "ELEVENLABS_API_KEY", {CostUnit.CHARS: 100}),
)


# One realistic build's worth of paid calls across all six providers — driven under a single tenant
# Anthropic key, so Claude bills to user_key and every other provider (no tenant key in scope) to
# platform. Kept as data so the mixed-build test reuses the same _record_and_drain path as the rest.
_MIXED_BUILD_CALLS: tuple[dict[str, object], ...] = (
    {
        "component": "planner",
        "provider": CostProvider.ANTHROPIC,
        "model": "claude-opus-4-8",
        "usage": {CostUnit.INPUT_TOKENS: 1000, CostUnit.OUTPUT_TOKENS: 500},
    },
    {
        "component": "grounding",
        "provider": CostProvider.VOYAGE,
        "model": "voyage-3.5",
        "usage": {CostUnit.INPUT_TOKENS: 8000},
    },
    {
        "component": "discovery",
        "provider": CostProvider.TAVILY,
        "model": None,
        "usage": {CostUnit.SEARCH: 4},
    },
    {
        "component": "cover",
        "provider": CostProvider.OPENAI,
        "model": "gpt-image-2",
        "usage": {CostUnit.IMAGES: 1},
    },
    {
        "component": "voice",
        "provider": CostProvider.ELEVENLABS,
        "model": None,
        "usage": {CostUnit.CHARS: 3000},
    },
    {
        "component": "render",
        "provider": CostProvider.MANIM,
        "model": None,
        "usage": {CostUnit.COMPUTE_SECONDS: 30.0},
    },
)


@pytest.mark.parametrize(
    "provider,model,env_var,usage",
    [
        pytest.param(provider, model, env_var, usage, id=name)
        for name, provider, model, env_var, usage in _KEYED_PROVIDERS
    ],
)
async def test_pocket_is_user_key_on_a_tenant_key_and_platform_otherwise(
    provider: CostProvider, model: str | None, env_var: str, usage: dict[CostUnit, float]
) -> None:
    # A deliberate contrast pair: pocket resolution follows key presence, so both halves (BYOK and
    # no-key) are the one concept — asserting only one wouldn't prove the discriminator.
    call = {"component": "stage", "provider": provider, "model": model, "usage": usage}

    # A run scope carrying the tenant's key bills this call to their pocket (BYOK).
    byok_store, _ = await _record_and_drain([call], credentials={env_var: "sk-tenant"})
    byok = await byok_store.list_for_course(course_id=_COURSE_ID)
    assert byok[0].pocket is CostPocket.USER_KEY

    # A scope without the key (the platform env path) bills it to the platform pocket.
    platform_store, _ = await _record_and_drain([call], credentials={})
    platform = await platform_store.list_for_course(course_id=_COURSE_ID)
    assert platform[0].pocket is CostPocket.PLATFORM


async def test_keyless_build_reads_as_free_but_measured() -> None:
    # Arrange — a keyless build: every stage ran on a local fallback (Qwen / bge / DuckDuckGo), each
    # priced to 0, but each still recorded so the total reads "~$0", not "no data".
    calls = [
        {
            "component": comp,
            "provider": CostProvider.LOCAL,
            "model": None,
            "usage": {CostUnit.INPUT_TOKENS: n},
        }
        for comp, n in (("planner", 1000), ("module_author", 5000), ("verifier", 2000))
    ]

    # Act
    _, cost_store = await _record_and_drain(calls)

    # Assert — a metered ~$0: a zero total, but three events, all local, all platform pocket.
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    assert rollup.total_amount == pytest.approx(0.0)
    assert rollup.breakdown["eventCount"] == 3
    assert set(rollup.breakdown["byProvider"]) == {"local"}
    assert rollup.breakdown["byPocket"]["platform"] == pytest.approx(0.0)
    assert rollup.breakdown["byPocket"]["user_key"] == pytest.approx(0.0)


async def test_mixed_build_rollup_equals_the_ledger_sum_across_providers_and_pockets() -> None:
    # Arrange / Act — a realistic build across all six paid providers, run on the tenant's Anthropic
    # key only (see _MIXED_BUILD_CALLS): Claude bills to user_key, the rest to platform.
    event_store, cost_store = await _record_and_drain(
        list(_MIXED_BUILD_CALLS), credentials={"ANTHROPIC_API_KEY": "sk-tenant"}
    )

    # Assert — the rollup total is exactly the sum of the whole ledger (the core invariant).
    ledger = await event_store.list_for_course(course_id=_COURSE_ID)
    rollup = await cost_store.get(course_id=_COURSE_ID)
    assert rollup is not None
    ledger_total = sum(event.amount for event in ledger)
    assert rollup.total_amount == pytest.approx(ledger_total)
    assert rollup.breakdown["eventCount"] == len(ledger)

    # Every paid provider is represented; the pocket split matches: only Claude on the tenant key.
    assert set(rollup.breakdown["byProvider"]) == {
        "anthropic",
        "voyage",
        "tavily",
        "openai",
        "elevenlabs",
        "manim",
    }
    claude_amount = next(e.amount for e in ledger if e.provider is CostProvider.ANTHROPIC)
    assert rollup.breakdown["byPocket"]["user_key"] == pytest.approx(claude_amount)
    assert rollup.breakdown["byPocket"]["platform"] == pytest.approx(ledger_total - claude_amount)
