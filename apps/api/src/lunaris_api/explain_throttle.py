from collections.abc import Callable
from datetime import UTC, datetime


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
        self._clock = clock or (lambda: datetime.now(UTC))
        # (owner_key, iso-day) -> explains admitted that day; pruned on each admit.
        self._counts: dict[tuple[str, str], int] = {}

    def admit(self, owner_key: str) -> None:
        """Admit one keyless explain for ``owner_key`` or raise the cap error (no release step)."""
        day = self._clock().date().isoformat()
        self._prune(day)
        used = self._counts.get((owner_key, day), 0)
        if used >= self._daily_cap:
            raise ExplainDailyCapReachedError(self._daily_cap)
        self._counts[(owner_key, day)] = used + 1

    def _prune(self, today: str) -> None:
        """Drop earlier days' counts so the cap resets and the map stays bounded."""
        stale = [key for key in self._counts if key[1] != today]
        for key in stale:
            del self._counts[key]
