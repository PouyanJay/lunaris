"""Unit tests for the versioned cost price book (course-cost-metering, T2).

The price book turns a metered unit count into a calculated cost. These pin the load-bearing
contracts: exact per-model Claude rates (with the cache read/write split that makes metering the
cache tokens worthwhile), provider-flat fallback for services not priced per model, keyless
``local`` pricing to $0, an un-priced lookup failing loudly (not silently to $0), and the version
stamp every cost row carries.
"""

import pytest
from lunaris_runtime.pricing import PRICE_BOOK_VERSION, PriceBook, Rate, UnknownRateError
from lunaris_runtime.schema import CostProvider, CostUnit


def test_current_book_carries_the_version_stamp() -> None:
    book = PriceBook.current()
    assert book.version == PRICE_BOOK_VERSION


def test_claude_token_rates_split_input_cache_and_output() -> None:
    # Arrange
    book = PriceBook.current()
    model = "claude-opus-4-8"  # $5/MTok in, $25/MTok out

    # Act
    per_input = book.rate(provider=CostProvider.ANTHROPIC, model=model, unit=CostUnit.INPUT_TOKENS)
    per_cache_read = book.rate(
        provider=CostProvider.ANTHROPIC, model=model, unit=CostUnit.CACHE_READ_TOKENS
    )
    per_cache_write = book.rate(
        provider=CostProvider.ANTHROPIC, model=model, unit=CostUnit.CACHE_WRITE_TOKENS
    )
    per_output = book.rate(
        provider=CostProvider.ANTHROPIC, model=model, unit=CostUnit.OUTPUT_TOKENS
    )

    # Assert — exact $/MTok converted to $/token, with cache read = 0.1x and cache write = 1.25x.
    assert per_input.amount_per_unit == pytest.approx(5.0 / 1_000_000)
    assert per_output.amount_per_unit == pytest.approx(25.0 / 1_000_000)
    assert per_cache_read.amount_per_unit == pytest.approx(per_input.amount_per_unit * 0.1)
    assert per_cache_write.amount_per_unit == pytest.approx(per_input.amount_per_unit * 1.25)
    assert per_input.currency == "USD"


def test_cost_multiplies_count_by_rate() -> None:
    # 1,000,000 input tokens on Opus 4.8 ($5/MTok) is exactly $5.
    book = PriceBook.current()
    cost = book.cost(
        provider=CostProvider.ANTHROPIC,
        model="claude-opus-4-8",
        unit=CostUnit.INPUT_TOKENS,
        count=1_000_000,
    )
    assert cost == pytest.approx(5.0)


def test_provider_flat_rate_falls_back_across_models() -> None:
    # Tavily search is priced flat (model=None); a lookup that names a model still resolves it.
    book = PriceBook.current()
    with_model = book.rate(provider=CostProvider.TAVILY, model="whatever", unit=CostUnit.SEARCH)
    without_model = book.rate(provider=CostProvider.TAVILY, model=None, unit=CostUnit.SEARCH)
    assert with_model == without_model
    assert with_model.amount_per_unit > 0


@pytest.mark.parametrize("unit", list(CostUnit))
def test_keyless_local_prices_every_unit_to_zero(unit: CostUnit) -> None:
    # A keyless build (Qwen/bge/DuckDuckGo) must read ~$0, so every local unit prices to 0
    # (parametrized so a regression names the offending unit, not one generic failure).
    book = PriceBook.current()
    assert book.cost(provider=CostProvider.LOCAL, model=None, unit=unit, count=1_000) == 0.0


def test_unknown_rate_raises_rather_than_silently_zero() -> None:
    # An un-priced call must fail loudly so the metering seam can log the miss — not silently $0.
    book = PriceBook.current()
    with pytest.raises(UnknownRateError):
        book.rate(provider=CostProvider.OPENAI, model="gpt-image-2", unit=CostUnit.OUTPUT_TOKENS)


def test_injected_rates_override_for_tests() -> None:
    # A test can pin an exact rate table instead of the checked-in one.
    book = PriceBook(
        version="test-v1",
        rates=[Rate(CostProvider.MANIM, None, CostUnit.COMPUTE_SECONDS, 0.01, "USD")],
    )
    assert book.version == "test-v1"
    assert book.cost(
        provider=CostProvider.MANIM, model=None, unit=CostUnit.COMPUTE_SECONDS, count=60
    ) == pytest.approx(0.60)
