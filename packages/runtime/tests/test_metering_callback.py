"""Unit tests for the LLM metering callback (course-cost-metering, T4).

The callback is the Claude cost seam: on each completion it splits ``usage_metadata`` into the four
priced token units and records the cost. The load-bearing case is the cache split — LangChain's
``input_tokens`` is the TOTAL (fresh + cache-read + cache-write), so the callback must back out the
fresh portion and price cache read / write separately (they cost ~0.1x / ~1.25x of fresh input).
"""

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from lunaris_runtime.metering import CostScope, cost_scope
from lunaris_runtime.metering.metering_callback import MeteringCallbackHandler
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostProvider

_OPUS = "claude-opus-4-8"  # $5/MTok in, $25/MTok out


def _result(usage: dict) -> LLMResult:
    # total_tokens is a required field of LangChain's UsageMetadata; the callback doesn't read it.
    full = {"total_tokens": (usage.get("input_tokens", 0) + usage.get("output_tokens", 0)), **usage}
    message = AIMessage(content="hi", usage_metadata=full)
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _scope() -> CostScope:
    return CostScope(run_id="r", course_id="c", price_book=PriceBook.current())


def test_callback_splits_cache_tokens_and_prices_them() -> None:
    # Arrange — a completion with fresh input, cache read, cache write, and output. LangChain's
    # input_tokens is the TOTAL input (fresh + both cache parts).
    scope = _scope()
    usage = {
        "input_tokens": 1_000_000,  # total input incl. cache
        "output_tokens": 100_000,
        "input_token_details": {"cache_read": 200_000, "cache_creation": 300_000},
    }
    handler = MeteringCallbackHandler(
        provider=CostProvider.ANTHROPIC, model=_OPUS, component="planner"
    )

    # Act
    with cost_scope(scope):
        handler.on_llm_end(_result(usage))

    # Assert — fresh input = 1,000,000 - 200,000 - 300,000 = 500,000, cache split kept separate.
    entry = scope.entries[0]
    assert entry.provider is CostProvider.ANTHROPIC
    assert entry.component == "planner"
    assert entry.usage == {
        "input_tokens": 500_000,
        "cache_read_tokens": 200_000,
        "cache_write_tokens": 300_000,
        "output_tokens": 100_000,
    }
    # amount = 500k*$5/M + 200k*$0.5/M + 300k*$6.25/M + 100k*$25/M
    expected = 500_000 * 5e-6 + 200_000 * 0.5e-6 + 300_000 * 6.25e-6 + 100_000 * 25e-6
    assert entry.amount == pytest.approx(expected)


def test_callback_without_cache_prices_fresh_input_only() -> None:
    scope = _scope()
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}  # no cache details
    handler = MeteringCallbackHandler(provider=CostProvider.ANTHROPIC, model=_OPUS, component="llm")
    with cost_scope(scope):
        handler.on_llm_end(_result(usage))
    assert scope.entries[0].usage == {"input_tokens": 1_000_000}
    assert scope.entries[0].amount == pytest.approx(5.0)


def test_local_completion_records_zero() -> None:
    # The keyless fallback is metered but prices to $0 (local), so a keyless build reads ~$0.
    scope = _scope()
    usage = {"input_tokens": 5_000, "output_tokens": 2_000}
    handler = MeteringCallbackHandler(provider=CostProvider.LOCAL, model=None, component="llm")
    with cost_scope(scope):
        handler.on_llm_end(_result(usage))
    assert scope.entries[0].provider is CostProvider.LOCAL
    assert scope.entries[0].amount == pytest.approx(0.0)


def test_callback_is_a_noop_without_a_scope() -> None:
    # Outside a build (no cost_scope), the callback records nothing and does not raise.
    handler = MeteringCallbackHandler(provider=CostProvider.ANTHROPIC, model=_OPUS, component="llm")
    handler.on_llm_end(_result({"input_tokens": 100, "output_tokens": 50}))  # must not raise


def test_callback_ignores_a_completion_with_no_usage() -> None:
    # A chunk/response carrying no usage_metadata records nothing (no zero-cost noise entry).
    scope = _scope()
    message = AIMessage(content="hi")  # usage_metadata is None
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    handler = MeteringCallbackHandler(provider=CostProvider.ANTHROPIC, model=_OPUS, component="llm")
    with cost_scope(scope):
        handler.on_llm_end(result)
    assert scope.entries == []
