from dataclasses import dataclass

from lunaris_runtime.schema import CostProvider, CostUnit


@dataclass(frozen=True)
class Rate:
    """One priced unit in the price book — "provider P (model M) charges $X per unit U".

    An internal domain value (a frozen dataclass, not a wire schema): the price book is reference
    data consumed inside Python to turn measured usage into a calculated cost, never sent over the
    wire. ``amount_per_unit`` is the cost of ONE ``unit`` in ``currency`` (e.g. dollars per token,
    per character, per image, per web search, per vCPU-second) — so ``cost = usage_count x
    amount_per_unit``. ``model`` is set for providers whose rate varies by model (Anthropic per
    tier) and ``None`` for providers priced flat across a call (search, TTS, images, render compute,
    the keyless ``local`` no-op).
    """

    provider: CostProvider
    model: str | None
    unit: CostUnit
    amount_per_unit: float
    currency: str
