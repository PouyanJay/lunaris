import structlog

from lunaris_runtime.pricing import PriceBook, UnknownRateError
from lunaris_runtime.schema import CostPocket, CostProvider, CostUnit

from .cost_entry import CostEntry
from .cost_scope import current_cost_scope
from .credential_pocket import credential_pocket

logger = structlog.get_logger()

# The BYOK env-var each paid provider authenticates on — the key whose presence in the run scope
# decides the pocket. Providers with no key (render compute, the keyless local no-op) bill to the
# platform pocket unconditionally. Kept in lockstep with the secret registry in
# apps/api/.../secrets/store.py (KNOWN_SECRETS) and capabilities/capability_spec.py — a provider
# env-var rename must update all three (grep the env-var name to catch drift).
_PROVIDER_ENV: dict[CostProvider, str] = {
    CostProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    CostProvider.VOYAGE: "EMBEDDINGS_API_KEY",
    CostProvider.TAVILY: "SEARCH_API_KEY",
    CostProvider.OPENAI: "OPENAI_API_KEY",
    CostProvider.ELEVENLABS: "ELEVENLABS_API_KEY",
}

# Soft cap on the in-memory scope buffer — mirrors CostEventRecorder.CAP_PER_RUN (the persisted cap
# applied at drain), so a runaway/looping build can't grow the buffer past what would ever persist.
_MAX_SCOPE_ENTRIES = 5000


def _price_usage(
    price_book: PriceBook,
    provider: CostProvider,
    model: str | None,
    usage: dict[CostUnit, float],
) -> tuple[float, dict[str, float]]:
    """Price a call's measured units into a total amount + the wire-shape usage dict.

    A unit with no rate is logged (``cost_rate_missing``) and priced 0 rather than raising — the
    "degrade honestly, never crash a build" half of the fail-loud/degrade-at-the-edge split. The
    returned usage keys are ``CostUnit`` values (the auditable form a ``CostEvent`` stores)."""
    amount = 0.0
    wire_usage: dict[str, float] = {}
    for unit, count in usage.items():
        wire_usage[unit.value] = count
        try:
            amount += price_book.cost(provider=provider, model=model, unit=unit, count=count)
        except UnknownRateError:
            logger.warning(
                "cost_rate_missing", provider=provider.value, model=model, unit=unit.value
            )
    return amount, wire_usage


def record_cost(
    *,
    component: str,
    provider: CostProvider,
    model: str | None,
    usage: dict[CostUnit, float],
) -> None:
    """Price one metered call and buffer it on the current run's cost scope.

    The one call every paid seam makes: it prices the measured units against the scope's price book,
    resolves the ``pocket`` from the credential scope, and appends a ``CostEntry``. A **no-op when
    no scope is active** (admin/eval/CLI/tests) — deep code calls it unconditionally and metering
    turns itself off outside a build.

    Must stay fully synchronous (no ``await``): the scope buffer is shared by a build task's
    contextvar copy and is lock-free precisely because nothing yields mid-append.
    """
    scope = current_cost_scope()
    if scope is None:
        return  # metering is off — no run scope
    if len(scope.entries) >= _MAX_SCOPE_ENTRIES:
        return  # runaway guard: past the cap the drain wouldn't persist it anyway
    amount, wire_usage = _price_usage(scope.price_book, provider, model, usage)
    env_var = _PROVIDER_ENV.get(provider)
    pocket = credential_pocket(env_var) if env_var is not None else CostPocket.PLATFORM
    scope.entries.append(
        CostEntry(
            component=component,
            provider=provider,
            model=model,
            usage=wire_usage,
            amount=amount,
            pocket=pocket,
        )
    )
