import re
from collections.abc import Iterable

from lunaris_runtime.schema import CostProvider, CostUnit

from .price_book_data import RATES
from .price_book_version import PRICE_BOOK_VERSION
from .rate import Rate
from .unknown_rate_error import UnknownRateError

# A model id may carry a snapshot-date suffix (`-20251001`) or a context-window marker (`[1m]`) that
# the price book keys by base model. Strip both so a pinned/long-context variant prices as its base
# rather than missing and silently pricing to $0. Order: drop the bracket marker, then a trailing
# 8-digit date.
_CONTEXT_SUFFIX = re.compile(r"\[[^\]]*\]$")
_SNAPSHOT_SUFFIX = re.compile(r"-\d{8}$")


def _base_model(model: str) -> str:
    """The base model id: any ``[1m]`` context marker and trailing ``-YYYYMMDD`` date dropped."""
    return _SNAPSHOT_SUFFIX.sub("", _CONTEXT_SUFFIX.sub("", model))


class PriceBook:
    """The versioned rate table: maps ``(provider, model, unit)`` to a per-unit ``Rate``.

    A lookup tries the exact ``(provider, model, unit)`` first, then falls back to
    ``(provider, None, unit)`` — the provider-flat rate for services not priced per model (search,
    TTS, images, render compute, the keyless ``local`` no-op). A build stamps ``version`` onto every
    cost row so a later rate change never rewrites the old total. Constructed from the checked-in
    ``price_book_data`` via ``current()``; an explicit rate list can be injected for tests.
    """

    def __init__(self, *, version: str, rates: Iterable[Rate]) -> None:
        self._version = version
        self._by_key: dict[tuple[CostProvider, str | None, CostUnit], Rate] = {}
        for rate in rates:
            key = (rate.provider, rate.model, rate.unit)
            # Fail loud on a duplicate (provider, model, unit) — a copy-paste in the rate table must
            # surface, not silently let the last entry win (the same "no silent wrong number" bar
            # the unknown-rate path holds).
            if key in self._by_key:
                raise ValueError(f"duplicate price-book rate for {key}")
            self._by_key[key] = rate

    @classmethod
    def current(cls) -> "PriceBook":
        """The checked-in price book (the one production builds price against)."""
        return cls(version=PRICE_BOOK_VERSION, rates=RATES)

    @property
    def version(self) -> str:
        return self._version

    def rate(self, *, provider: CostProvider, model: str | None, unit: CostUnit) -> Rate:
        """The per-unit rate for a metered call. Exact ``(provider, model, unit)`` wins; else the
        same model with any snapshot/context suffix stripped; else the provider-flat
        ``(provider, None, unit)``; else ``UnknownRateError``."""
        exact = self._by_key.get((provider, model, unit))
        if exact is not None:
            return exact
        if model is not None:
            normalized = self._normalized_rate(provider, model, unit)
            if normalized is not None:
                return normalized
        flat = self._by_key.get((provider, None, unit))
        if flat is not None:
            return flat
        raise UnknownRateError(
            f"no rate for provider={provider.value} model={model} unit={unit.value}"
        )

    def _normalized_rate(self, provider: CostProvider, model: str, unit: CostUnit) -> Rate | None:
        """The rate for the model's base id (snapshot/context suffix stripped), or ``None`` when the
        id has no suffix or its base isn't priced — so a pinned/long-context variant prices as its
        base model rather than silently missing to $0."""
        base = _base_model(model)
        if base == model:
            return None
        return self._by_key.get((provider, base, unit))

    def cost(
        self, *, provider: CostProvider, model: str | None, unit: CostUnit, count: float
    ) -> float:
        """The calculated cost of ``count`` units — ``count x amount_per_unit``. Raises
        ``UnknownRateError`` if the unit is un-priced (the caller decides how to degrade)."""
        return count * self.rate(provider=provider, model=model, unit=unit).amount_per_unit
