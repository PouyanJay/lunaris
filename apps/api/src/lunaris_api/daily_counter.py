"""The counting primitive every per-day cap in this API is built on.

Three throttles now ration something per tenant per day — keyless builds, explains, and Lunaris
Live's compiles and extensions — and each had grown its own copy of the same two mechanics: a
``(key, iso-day)`` bucket, and a prune that drops earlier days on the way past. The *policies*
differ and should (what is rationed, what the cap is, what a learner is told when they hit it);
the counting does not.

Deliberately not a throttle: it has no notion of refusal, no message, and no HTTP status. It
answers "how many today" and "one more" — every decision about what that means stays with the
throttle that owns the policy.
"""

from collections.abc import Callable
from datetime import UTC, datetime


class DailyCounter:
    """Counts admissions per key per UTC day, pruning earlier days as it goes.

    Pruning on write is what keeps this bounded without a background sweep: a process that runs for
    a year holds at most one day's keys, because every entry from an earlier day is dropped the
    first time anything is counted on the next one.

    ``clock`` is injectable so a test can prove the daily reset instead of waiting for midnight.
    """

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._counts: dict[tuple[str, str], int] = {}

    def used(self, key: str) -> int:
        """How many admissions ``key`` has had today. Prunes earlier days as a side effect, so
        every read keeps the map bounded even if nothing is ever counted again."""
        day = self._today()
        self._prune(day)
        return self._counts.get((key, day), 0)

    def count(self, key: str) -> None:
        """Record one admission for ``key`` today. Deliberately separate from :meth:`used` so a
        caller can check a cap, refuse, and *not* count the request it refused."""
        day = self._today()
        self._counts[(key, day)] = self._counts.get((key, day), 0) + 1

    def _today(self) -> str:
        return self._clock().date().isoformat()

    def _prune(self, today: str) -> None:
        for key in [key for key in self._counts if key[1] != today]:
            del self._counts[key]
