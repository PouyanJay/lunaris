from collections.abc import Callable
from datetime import datetime

from .daily_counter import DailyCounter


class ExplainDailyCapReachedError(Exception):
    """A keyless caller used up today's explanations; the route maps this to a 429."""

    def __init__(self, cap: int) -> None:
        super().__init__(
            f"You've used today's {cap} included explanations. They reset tomorrow — or add your "
            "own Anthropic key in Settings (or switch Explain to run on this device) for "
            "unlimited explanations."
        )


class KeylessExplainThrottle:
    """In-process per-user daily cap for server-fallback explains.

    The keyless build throttle's small sibling: explains are seconds of compute (not minutes), so
    there is no concurrency limit and no reservation to release — one synchronous count per
    successful admission, pruned to the current UTC day. Hosted (keyed) explains never consult
    this; builds have their own budget (``KeylessBuildThrottle``) — the two are never shared.
    """

    def __init__(
        self,
        *,
        daily_cap: int = 50,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._daily_cap = daily_cap
        self._counts = DailyCounter(clock=clock)

    def admit(self, owner_key: str) -> None:
        """Admit one keyless explain for ``owner_key`` or raise the cap error (no release step)."""
        if self._counts.used(owner_key) >= self._daily_cap:
            raise ExplainDailyCapReachedError(self._daily_cap)
        self._counts.count(owner_key)
