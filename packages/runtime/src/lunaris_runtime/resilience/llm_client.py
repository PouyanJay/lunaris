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

_rate_limiter: "BaseRateLimiter | None" = None


def get_llm_rate_limiter() -> "BaseRateLimiter":
    """The process-wide token-bucket rate limiter shared by every live Claude client.

    Returns the same instance on every call so all adapters draw from one budget.
    ``requests_per_second`` comes from ``LUNARIS_LLM_RPS`` (default 0.7). Constructed lazily so
    importing this module needs no ``langchain_core`` and tests that never go live pay nothing.
    """
    global _rate_limiter
    if _rate_limiter is None:
        import os

        from langchain_core.rate_limiters import InMemoryRateLimiter

        rps = float(os.getenv("LUNARIS_LLM_RPS", _DEFAULT_LLM_RPS))
        _rate_limiter = InMemoryRateLimiter(
            requests_per_second=rps,
            check_every_n_seconds=0.1,
            max_bucket_size=max(1.0, rps),
        )
    return _rate_limiter


def build_anthropic_chat_model(model_id: str) -> "BaseChatModel":
    """A live ``ChatAnthropic`` wired with the shared hardening — the one place the knobs are set.

    Every live Claude adapter needs the same timeout + bounded retries + shared rate limiter; this
    factory bundles them so each adapter's ``_chat_model`` is a one-liner rather than a copy. It
    imports ``langchain_anthropic`` lazily so only the live path pays for it (tests inject a model).

    This is also the single Anthropic key-injection point (BYOK): ``api_key`` is resolved from the
    current run's credential scope when one is active (the tenant's own key), else from the process
    environment (admin/eval/single-user). Passing ``None`` is identical to the prior behaviour —
    ``ChatAnthropic`` then reads ``ANTHROPIC_API_KEY`` itself — and only happens with no scope and
    no env key set, the same failure as before; a tenant build is refused upstream when its key is
    missing, so a scoped build always has a non-``None`` key here.

    The key value is never logged here; redaction at the structlog layer covers it regardless.
    """
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model_id,
        api_key=resolve_secret("ANTHROPIC_API_KEY"),
        default_request_timeout=LLM_REQUEST_TIMEOUT_S,
        max_retries=LLM_MAX_RETRIES,
        rate_limiter=get_llm_rate_limiter(),
    )
