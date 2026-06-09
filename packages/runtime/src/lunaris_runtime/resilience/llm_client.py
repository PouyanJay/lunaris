"""Shared hardening for every live LLM client: a request timeout, bounded retries, and one
process-wide rate limiter.

Two failure modes this guards:

1. **Hang.** The Anthropic SDK's request timeout defaults to ``None`` — a stalled socket then hangs
   the call (and, with no overall wall-clock bound, the whole agent run) forever. Every live Claude
   adapter sets ``default_request_timeout`` so a dead connection fails fast and the app-level
   ``retry_on_rate_limit`` / the agent's own retry can recover.
2. **Sustained over-quota.** The agent fans many calls out fast (e.g. the O(n²) pairwise
   prerequisite judgments); a concurrency cap bounds *in-flight* calls but not *throughput*, so the
   burst still trips the account's requests-per-minute tier. A single shared
   ``InMemoryRateLimiter`` — one instance across every adapter in every package — paces *all* live
   Claude calls under that ceiling. ``retry_on_rate_limit`` remains the safety net for the
   occasional 429 that still slips through.

The values live here so they are set in one place. ``langchain_core`` is imported lazily inside the
factory (only the live path needs it), so ``lunaris_runtime``'s declared dependencies stay light.
"""

import math
import os
from typing import TYPE_CHECKING

from lunaris_runtime.credentials import resolve_secret

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.rate_limiters import BaseRateLimiter

# Per-request timeout (seconds). Individual Claude calls complete well under this; the bound exists
# to turn a hung socket into a prompt, recoverable error.
LLM_REQUEST_TIMEOUT_S = 60.0

# Bounded SDK-level retries for transient connection/5xx failures. Rate-limit (429) backoff is
# handled separately by ``retry_on_rate_limit``; this is a small safety net on top.
LLM_MAX_RETRIES = 2

# Sustained request budget (requests/second). Default ≈720 req/min — under Anthropic's Tier-2
# 1000 req/min while the shared limiter + ``retry_on_rate_limit`` absorb any overshoot. Lower it via
# ``LUNARIS_LLM_RPS`` on the base 50/min tier (e.g. 0.7); raise it on a higher tier.
_DEFAULT_LLM_RPS = 12.0

# Keyless local LLM fallback (Qwen2.5-3B-Instruct by default — a small, strong tool-calling model
# whose GQA keeps it light enough to fit a 4 GiB serverless-CPU container), reached over an
# OpenAI-compatible endpoint when no Anthropic key is configured. The defaults target a local
# llama.cpp server; both are overridable so swapping the model or runtime is a one-line env change.
_DEFAULT_FALLBACK_BASE_URL = "http://localhost:8080/v1"
_DEFAULT_FALLBACK_MODEL = "qwen2.5-3b-instruct"
# llama.cpp ignores the key, but the OpenAI client requires a non-empty value. A placeholder, NOT a
# secret — the whole point of the fallback is that it needs no API key.
_FALLBACK_PLACEHOLDER_KEY = "no-key-required"

# Keyless CPU inference is far slower than a hosted API, so the keyless path gets its own generous
# timeouts (the 60s hosted bound would cancel a keyless call mid-prefill). Prefilling a
# multi-thousand-token agent prompt on a 2-vCPU container runs *minutes* before the first token —
# measured ~26 tok/s on prod Qwen-3B, so a ~7.9k-token prompt needs ~5 min to its first chunk, well
# past ``langchain_openai``'s 120s ``stream_chunk_timeout`` default (which silently cancelled the
# first build call). ``stream_chunk_timeout`` bounds the wait for that first/next chunk; the overall
# request timeout must additionally cover a full generation. Both are env-tunable per box.
_DEFAULT_FALLBACK_REQUEST_TIMEOUT_S = 900.0
_DEFAULT_FALLBACK_STREAM_CHUNK_TIMEOUT_S = 600.0

# The keyless model's context window, in tokens — must match the served endpoint's --ctx-size
# (16384 on the deployed llama.cpp container). A small local model has a *tiny* window next to a
# hosted Claude's, and the deep-agent planner accumulates context (todo list + tool results) that
# silently overflowed it mid-build (400 exceed_context_size_error). Advertising the window via the
# model's `profile` makes deepagents size its summarization to a fraction of it (summarize before
# the limit) instead of its fixed 170k-token fallback for unknown models — which never fires in 16k.
_DEFAULT_FALLBACK_CONTEXT_TOKENS = 16384
# Tokens reserved for the model's own response so input + output stay within the window; the profile
# advertises `window - reserve` as the max *input*. 2048 is a conservative bound for a build's
# tool-call / structured-output responses, which rarely run longer.
_FALLBACK_RESPONSE_RESERVE_TOKENS = 2048
# Floor for the advertised input budget, so a misconfigured (tiny) window can't drive it to zero.
_FALLBACK_MIN_INPUT_TOKENS = 1024

_rate_limiter: "BaseRateLimiter | None" = None


def _env_float(name: str, default: float) -> float:
    """A positive float from env ``name``, falling back to ``default`` when unset or invalid.

    These knobs (timeouts, request rate) are operationally tuned via env, so a typo'd override —
    non-numeric, non-finite (``inf``), or non-positive (``0``/``-1``) — must default safely rather
    than crash the build or wedge a client with a nonsensical bound.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except (ValueError, OverflowError):
        return default
    return value if math.isfinite(value) and value > 0 else default


def _env_int(name: str, default: int) -> int:
    """A positive int from env ``name``, falling back to ``default`` when unset or invalid.

    Like ``_env_float`` but for integer-valued knobs (e.g. token counts): a non-integer or
    non-positive value defaults safely rather than crashing or silently truncating a float.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def get_llm_rate_limiter() -> "BaseRateLimiter":
    """The process-wide token-bucket rate limiter shared by every live Claude client.

    Returns the same instance on every call so all adapters draw from one budget.
    ``requests_per_second`` comes from ``LUNARIS_LLM_RPS`` (default 0.7). Constructed lazily so
    importing this module needs no ``langchain_core`` and tests that never go live pay nothing.
    """
    global _rate_limiter
    if _rate_limiter is None:
        from langchain_core.rate_limiters import InMemoryRateLimiter

        rps = _env_float("LUNARIS_LLM_RPS", _DEFAULT_LLM_RPS)
        _rate_limiter = InMemoryRateLimiter(
            requests_per_second=rps,
            check_every_n_seconds=0.1,
            max_bucket_size=max(1.0, rps),
        )
    return _rate_limiter


def build_chat_model(model_id: str) -> "BaseChatModel":
    """The hardened chat model for a run — the one place the LLM provider is chosen.

    Two paths, both wired with the same timeout + bounded retries + shared rate limiter:

    1. **Live (Anthropic key present).** A ``ChatAnthropic`` on ``model_id``. This is the single
       Anthropic key-injection point (BYOK): the key is resolved from the current run's credential
       scope when one is active (the tenant's own key), else from the process environment
       (admin/eval/single-user). ``langchain_anthropic`` is imported lazily so only the live path
       pays for it.
    2. **Keyless fallback (no Anthropic key anywhere).** A local OpenAI-compatible endpoint
       (Qwen2.5-3B-Instruct by default) so a keyless account still builds (a labelled "Draft").
       ``model_id`` (a Claude id) is ignored in favour of the configured fallback model. No key.

    The key value is never logged here; redaction at the structlog layer covers it regardless.
    """
    anthropic_key = resolve_secret("ANTHROPIC_API_KEY")
    if not anthropic_key:  # None or "" → no live key → the keyless fallback, not a blank-key Claude
        return build_keyless_chat_model()

    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model_id,
        api_key=anthropic_key,
        default_request_timeout=LLM_REQUEST_TIMEOUT_S,
        max_retries=LLM_MAX_RETRIES,
        rate_limiter=get_llm_rate_limiter(),
    )


def build_keyless_chat_model() -> "BaseChatModel":
    """The keyless local fallback model over an OpenAI-compatible endpoint (Qwen2.5-3B by default).

    Public so the keyless path can be requested directly (e.g. the tool-calling smoke check), as
    distinct from ``build_chat_model``, which routes to Claude when a key is present.

    Base URL + model id come from ``LUNARIS_FALLBACK_LLM_BASE_URL`` / ``LUNARIS_FALLBACK_LLM_MODEL``
    (defaults target a local llama.cpp server), so swapping the model or runtime is a one-line env
    change. The ``api_key`` is a non-secret placeholder — the endpoint ignores it.

    The model is a ``RepairingChatOpenAI`` (T1b): a small local model's tool-call JSON is its weak
    spot, so its completions have malformed tool calls repaired before the agent acts on them.
    ``langchain_openai`` (via that subclass) is imported lazily so only the fallback path pays it.
    """
    from .repaired_chat_model import RepairingChatOpenAI

    window = _env_int("LUNARIS_FALLBACK_LLM_CONTEXT_TOKENS", _DEFAULT_FALLBACK_CONTEXT_TOKENS)
    max_input_tokens = max(_FALLBACK_MIN_INPUT_TOKENS, window - _FALLBACK_RESPONSE_RESERVE_TOKENS)

    return RepairingChatOpenAI(
        model=os.getenv("LUNARIS_FALLBACK_LLM_MODEL", _DEFAULT_FALLBACK_MODEL),
        base_url=os.getenv("LUNARIS_FALLBACK_LLM_BASE_URL", _DEFAULT_FALLBACK_BASE_URL),
        api_key=_FALLBACK_PLACEHOLDER_KEY,
        timeout=_env_float("LUNARIS_FALLBACK_LLM_TIMEOUT_S", _DEFAULT_FALLBACK_REQUEST_TIMEOUT_S),
        stream_chunk_timeout=_env_float(
            "LUNARIS_FALLBACK_LLM_STREAM_CHUNK_TIMEOUT_S",
            _DEFAULT_FALLBACK_STREAM_CHUNK_TIMEOUT_S,
        ),
        max_retries=LLM_MAX_RETRIES,
        rate_limiter=get_llm_rate_limiter(),
        # Advertise the small context window so the deep-agent harness summarizes a fraction before
        # the limit instead of overflowing it (deepagents falls back to a 170k trigger otherwise).
        profile={"max_input_tokens": max_input_tokens},
    )
