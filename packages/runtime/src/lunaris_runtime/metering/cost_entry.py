from dataclasses import dataclass

from lunaris_runtime.schema import CostPocket, CostProvider


@dataclass(frozen=True)
class CostEntry:
    """One priced metered call, buffered on the run's cost scope until the build drains it.

    An internal domain value (frozen dataclass): ``record_cost`` computes it at the paid-call site —
    the ``amount`` is already calculated (``usage`` counts x the price-book rate) and the ``pocket``
    already resolved from the credential scope — and appends it to the scope's buffer. At the build
    boundary the buffer is drained into the ``CostEventRecorder`` (ledger + rollup). ``usage`` uses
    ``CostUnit`` string values as keys (the wire shape a ``CostEvent`` stores) so the calculation
    stays auditable against the rate.
    """

    component: str
    provider: CostProvider
    model: str | None
    usage: dict[str, float]  # CostUnit value -> measured count
    amount: float
    pocket: CostPocket
