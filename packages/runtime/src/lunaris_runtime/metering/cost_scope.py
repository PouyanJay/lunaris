"""The per-run cost scope — where deep pipeline code records what a build spends.

Paid calls happen deep in the pipeline (the LLM client in ``resilience``, the grounding/video/cover
adapters), far below the API layer that owns the store. So — mirroring ``run_credentials`` — the run
carries a cost scope in a ``ContextVar`` entered at the same build boundary where the credential
scope is entered. ``record_cost`` (deep, synchronous) prices a call and appends it to the scope's
buffer; the build boundary drains the buffer into the ``CostEventRecorder`` (ledger + rollup) at
the end. With no scope active (admin/eval/CLI/tests), ``record_cost`` is a no-op — metering is
simply off.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from lunaris_runtime.pricing import PriceBook

from .cost_entry import CostEntry


@dataclass
class CostScope:
    """A running build's cost context: attribution + the price book + the buffered entries.

    Carries the ``run_id`` / ``course_id`` a cost is stamped with, the ``owner_id`` it belongs to,
    the ``PriceBook`` ``record_cost`` prices against (its ``version`` is stamped on every row), the
    display ``currency``, and the ``entries`` buffer deep code appends to. One scope per build task,
    so the buffer needs no locking (a task's contextvar copy is private to it).
    """

    run_id: str
    course_id: str
    price_book: PriceBook
    owner_id: str | None = None
    currency: str = "USD"
    # Grows for the build's lifetime; the drain caps what's *persisted* at CostEventRecorder's
    # CAP_PER_RUN. A soft buffer cap belongs here once the recorder is wired into a real build (T4)
    # — a runaway build could otherwise grow this in memory before the drain trims it.
    entries: list[CostEntry] = field(default_factory=list)


_cost_scope: ContextVar[CostScope | None] = ContextVar("lunaris_cost_scope", default=None)


def current_cost_scope() -> CostScope | None:
    """The running build's cost scope, or ``None`` when metering is off (no scope entered)."""
    return _cost_scope.get()


@contextmanager
def cost_scope(scope: CostScope) -> Iterator[CostScope]:
    """Bind ``scope`` as the current build's cost scope for the block.

    Enter this around the build task (beside ``run_credentials``) so the task inherits a context
    copy carrying the scope; the token-based reset restores the prior context on exit."""
    token = _cost_scope.set(scope)
    try:
        yield scope
    finally:
        _cost_scope.reset(token)
