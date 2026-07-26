"""The LangChain callback that meters every LLM call — the Claude (and keyless) cost seam.

Attached to the chat model in ``build_chat_model`` (one handler per built model), so it fires on
every invocation of that model wherever the pipeline calls it (deep-agent planner, subagents,
judges) without threading anything through each call site. On each completion it reads the
standardized ``usage_metadata`` and calls ``record_cost`` — a no-op outside a build scope.

``run_inline = True`` is load-bearing: it makes the callback run in the invoking coroutine's context
(not a thread-pool executor), so ``record_cost`` sees the run's ``cost_scope`` contextvar. The
handler stays fully synchronous (no ``await``), honouring ``record_cost``'s no-yield invariant.
"""

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from lunaris_runtime.schema import CostProvider, CostUnit

from .record_cost import record_cost


def _extract_usage(response: LLMResult) -> dict[CostUnit, float]:
    """Split a completion's token usage into the four priced units, summed across generations.

    LangChain's ``usage_metadata.input_tokens`` is the TOTAL input (Anthropic's base input PLUS
    cache-read and cache-creation), so fresh (uncached) input is the total minus the two cache
    parts — priced separately because cache read (~0.1x) and cache write (~1.25x) cost very
    differently from fresh input. Returns only the units that occurred (a zero unit is dropped)."""
    fresh = cache_read = cache_write = output = 0.0
    for generation_list in response.generations:
        for generation in generation_list:
            usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
            if not usage:
                continue
            details = usage.get("input_token_details") or {}
            read = details.get("cache_read") or 0
            # Prefer the explicit 5m+1h split; fall back to the generic cache_creation total.
            write = (details.get("ephemeral_5m_input_tokens") or 0) + (
                details.get("ephemeral_1h_input_tokens") or 0
            )
            if write == 0:
                write = details.get("cache_creation") or 0
            total_input = usage.get("input_tokens") or 0
            fresh += max(0, total_input - read - write)
            cache_read += read
            cache_write += write
            output += usage.get("output_tokens") or 0
    counts = {
        CostUnit.INPUT_TOKENS: fresh,
        CostUnit.CACHE_READ_TOKENS: cache_read,
        CostUnit.CACHE_WRITE_TOKENS: cache_write,
        CostUnit.OUTPUT_TOKENS: output,
    }
    return {unit: count for unit, count in counts.items() if count > 0}


class MeteringCallbackHandler(BaseCallbackHandler):
    """Records the cost of every completion from the model it's attached to.

    Constructed with the model's ``provider`` (``ANTHROPIC`` live, ``LOCAL`` for the keyless/device
    fallback), its ``model`` id (``None`` for local), and the ``component`` the model serves. Local
    completions still record (usage priced to $0) so a keyless build honestly reads ~$0.
    """

    # Run in the invoking context (not an executor) so record_cost sees the cost_scope contextvar.
    run_inline = True

    def __init__(self, *, provider: CostProvider, model: str | None, component: str) -> None:
        self._provider = provider
        self._model = model
        self._component = component

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = _extract_usage(response)
        if not usage:
            return  # a completion with no reported usage records nothing (no $0 noise entry)
        record_cost(
            component=self._component,
            provider=self._provider,
            model=self._model,
            usage=usage,
        )
