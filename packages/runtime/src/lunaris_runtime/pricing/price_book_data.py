"""The versioned price-book data — static per-unit rates, sourced from provider pricing pages.

This is *reference data*, edited here (not in code) when a provider changes prices. Every recorded
cost stamps ``PRICE_BOOK_VERSION`` so old costs stay pinned to the rates they were priced under —
bump the version whenever a rate below changes.

Rate provenance:
  * Anthropic (exact, first-party API $/MTok): Opus 4.8/4.7 $5/$25 in/out; Sonnet 5 $3/$15 (intro
    $2/$10 through 2026-08-31 — using the standard rate here, trued at invoice); Haiku 4.5 $1/$5.
    Cache read ~= 0.1x input; cache write (5-minute TTL, the default) ~= 1.25x input.
  * Voyage / Tavily / OpenAI GPT Image / ElevenLabs / Azure ACA: APPROXIMATE public rates — verify
    against the current provider pricing page and true up against a real invoice before these totals
    are trusted beyond an order-of-magnitude. Tier-dependent rates (ElevenLabs per-char, ACA
    $/vCPU-s) are placeholders for the account's actual tier.
  * ``local`` (Qwen / bge / DuckDuckGo / device bridge): 0 — keyless fallbacks cost the platform
    nothing, so a keyless build honestly reads ~$0.
"""

from lunaris_runtime.schema import CostProvider, CostUnit

from .rate import Rate

# Bump whenever any rate below changes (a build stamps this onto every cost row).
PRICE_BOOK_VERSION = "2026-07-25"

_USD = "USD"


def _per_mtok(usd_per_million: float) -> float:
    """A $/MTok headline rate as dollars per single token (the price book's per-unit currency)."""
    return usd_per_million / 1_000_000


def _anthropic(model: str, *, mtok_in: float, mtok_out: float) -> list[Rate]:
    """The four token rates for a Claude model: fresh input, cache-read, cache-write (5m), output.

    Cache read is ~0.1x input; cache write (default 5-minute TTL) is ~1.25x input — the two knobs
    that make metering ``cache_read_input_tokens`` / ``cache_creation_input_tokens`` separately
    matter for the cache-heavy author->verify->revise loop.
    """
    return [
        Rate(CostProvider.ANTHROPIC, model, CostUnit.INPUT_TOKENS, _per_mtok(mtok_in), _USD),
        Rate(
            CostProvider.ANTHROPIC,
            model,
            CostUnit.CACHE_READ_TOKENS,
            _per_mtok(mtok_in) * 0.1,
            _USD,
        ),
        Rate(
            CostProvider.ANTHROPIC,
            model,
            CostUnit.CACHE_WRITE_TOKENS,
            _per_mtok(mtok_in) * 1.25,
            _USD,
        ),
        Rate(CostProvider.ANTHROPIC, model, CostUnit.OUTPUT_TOKENS, _per_mtok(mtok_out), _USD),
    ]


RATES: tuple[Rate, ...] = (
    # --- Anthropic / Claude (exact first-party $/MTok) -----------------------------------------
    *_anthropic("claude-opus-4-8", mtok_in=5.0, mtok_out=25.0),
    *_anthropic("claude-opus-4-7", mtok_in=5.0, mtok_out=25.0),
    *_anthropic("claude-sonnet-5", mtok_in=3.0, mtok_out=15.0),
    *_anthropic("claude-sonnet-4-6", mtok_in=3.0, mtok_out=15.0),
    *_anthropic("claude-haiku-4-5", mtok_in=1.0, mtok_out=5.0),
    # --- Voyage embeddings (voyage-3.5, ~$0.06/MTok — approximate) ------------------------------
    Rate(CostProvider.VOYAGE, "voyage-3.5", CostUnit.INPUT_TOKENS, _per_mtok(0.06), _USD),
    # --- Tavily web search (~$0.008 per search — approximate, plan-dependent) -------------------
    Rate(CostProvider.TAVILY, None, CostUnit.SEARCH, 0.008, _USD),
    # --- OpenAI GPT Image 2 (2048x1152 high, ~$0.30/image — approximate) ------------------------
    Rate(CostProvider.OPENAI, "gpt-image-2", CostUnit.IMAGES, 0.30, _USD),
    # --- ElevenLabs TTS (~$0.0003 per character — approximate, account-tier dependent) ----------
    Rate(CostProvider.ELEVENLABS, None, CostUnit.CHARS, 0.0003, _USD),
    # --- Manim render compute (Azure ACA, ~$0.0000024 per vCPU-second — approximate) ------------
    Rate(CostProvider.MANIM, None, CostUnit.COMPUTE_SECONDS, 0.0000024, _USD),
    # --- Keyless local fallbacks: free to the platform (every unit prices to 0) -----------------
    *(Rate(CostProvider.LOCAL, None, unit, 0.0, _USD) for unit in CostUnit),
)
