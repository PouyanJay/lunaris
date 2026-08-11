"""Admission control for Lunaris Live's compile plane (Phase 1, T8c / D4).

Live spends money on two triggers, and they are rationed differently because they are different
risks:

- a **cold compile** is minutes of provider calls, asked for by an owner naming a topic. It is
  capped **per owner**: one in flight at a time (a second is almost always a double-submit, and two
  overlapping compiles double the burst against the org's rate limit) plus a per-day allowance.
- an **extension** is C1's runtime branch compile, asked for by the *conversation*. It is capped
  **per graph**, because a session works one map and the runaway this guards against is one
  conversation asking that map to grow without end.

The money cap itself is not here: a graph's spend is a number the ledger already keeps, so it is
read from the rollup by the service (which owns the cost stores) rather than counted a second time
in memory. Its refusal shares this module's error family so the routers keep one ``except``.

Like the Draft and Explain throttles this is an **in-process** gate: the counters live in memory, so
they reset on restart and do not coordinate across replicas — sufficient for the current
single-replica deploy, with a DB-backed ledger as the documented upgrade path.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ..daily_counter import DailyCounter
from .work_refused import LiveWorkRefusedError


class LiveCompileBusyError(LiveWorkRefusedError):
    """A compile is already running for this owner; a second pays for the same minutes twice."""

    detail = (
        "A map is already being built for you. It keeps going even if this page lost the "
        "connection — reopen it rather than starting a second one."
    )


class LiveCompileDailyCapReachedError(LiveWorkRefusedError):
    """The owner has used their per-day allowance of cold compiles."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.detail = (
            f"You've built today's {cap} maps. They reset tomorrow — the maps you already have "
            "stay open, and you can keep growing them."
        )
        super().__init__(self.detail)


class LiveExtendCapReachedError(LiveWorkRefusedError):
    """This graph has been grown as many times today as it is allowed to be."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.detail = (
            f"This map has grown {cap} times today, which is as far as it goes. Start a new map "
            "for a different subject, or come back tomorrow."
        )
        super().__init__(self.detail)


class LiveGraphBudgetExhaustedError(LiveWorkRefusedError):
    """The graph has spent its budget, read from the ledger's rollup.

    Raised by the service rather than the throttle — the number lives in the ledger, not in memory
    — but it belongs to the same refusal family so the routers answer it identically.
    """

    def __init__(self, *, spent: float, cap: float) -> None:
        self.spent = spent
        self.cap = cap
        self.detail = (
            "This map has used its full build budget. Start a new map for a different subject, or "
            "ask an administrator to raise the limit."
        )
        super().__init__(self.detail)


@dataclass(frozen=True)
class CompileSlot:
    """A held cold-compile slot. Release it when the compile ends — success or failure."""

    owner_key: str


class LiveGraphThrottle:
    """In-process admission gate for Live's compiles and extensions.

    Admissions are synchronous (nothing is awaited), so check-and-reserve is atomic under the
    single-threaded event loop and needs no lock.
    """

    def __init__(
        self,
        *,
        compile_daily_cap: int = 20,
        compile_max_concurrent: int = 1,
        extend_daily_cap: int = 50,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._compile_daily_cap = compile_daily_cap
        # At least one — a 0 would refuse every compile as "busy", which is a lie about why. An
        # operator turning Live off does it at the feature flag, not by zeroing a concurrency dial.
        self._compile_max_concurrent = max(1, compile_max_concurrent)
        self._extend_daily_cap = extend_daily_cap
        # owner_key -> compiles in flight right now. Not a daily count: it rises and falls with the
        # work itself, and is the one number here that must go back down.
        self._compiling: dict[str, int] = {}
        # Two separate counters because they are counted on different axes — compiles per owner,
        # extensions per graph — and one map keyed by both would let a graph id collide with an
        # owner id and quietly share an allowance.
        self._compiles = DailyCounter(clock=clock)
        self._extensions = DailyCounter(clock=clock)

    def reserve_compile(self, owner_key: str) -> CompileSlot:
        """Admit one cold compile for ``owner_key``, or refuse with the reason.

        Raises :class:`LiveCompileBusyError` when this owner already has one running, or
        :class:`LiveCompileDailyCapReachedError` when they have used the day's allowance. The caller
        MUST :meth:`release_compile` when the compile ends.
        """
        if self._compiling.get(owner_key, 0) >= self._compile_max_concurrent:
            raise LiveCompileBusyError
        if self._compiles.used(owner_key) >= self._compile_daily_cap:
            raise LiveCompileDailyCapReachedError(self._compile_daily_cap)
        self._compiles.count(owner_key)
        self._compiling[owner_key] = self._compiling.get(owner_key, 0) + 1
        return CompileSlot(owner_key=owner_key)

    def release_compile(self, slot: CompileSlot) -> None:
        """Free the in-flight slot. The day's count is deliberately NOT decremented — a finished
        compile has still spent its money, and refunding it would leave the daily cap bounding
        nothing but concurrency. Safe to call twice (floors at zero)."""
        remaining = self._compiling.get(slot.owner_key, 0) - 1
        if remaining > 0:
            self._compiling[slot.owner_key] = remaining
        else:
            self._compiling.pop(slot.owner_key, None)

    def admit_extension(self, graph_id: str) -> None:
        """Admit one runtime extension of ``graph_id``, or raise :class:`LiveExtendCapReachedError`.

        No reservation to release: an extension is bounded to seconds by C1's own deadline, so what
        needs rationing is how many of them a conversation may ask for, not how many run at once.
        """
        if self._extensions.used(graph_id) >= self._extend_daily_cap:
            raise LiveExtendCapReachedError(self._extend_daily_cap)
        self._extensions.count(graph_id)
