"""Admission control for keyless ("Draft") builds (keyless-fallbacks T6).

A keyless build runs on a slow, shared, self-hosted runtime (a small model on CPU), so — unlike a
keyed build, which hits the fast hosted provider — it must be rationed:

- an **operator switch** can disable the Draft tier entirely (``LUNARIS_DRAFT_TIER_ENABLED``);
- each signed-in tenant gets a **per-day cap** (``LUNARIS_DRAFT_DAILY_CAP``) so one user can't
  exhaust the runtime for everyone; and
- builds are **serialized** to ``LUNARIS_DRAFT_MAX_CONCURRENT`` (default 1) in-flight at a time, so
  a burst of Draft builds is refused rather than piled onto the runtime.

This is an in-process gate: the counters live in memory, so they reset on restart and do not
coordinate across replicas. That is sufficient for the current single-replica deploy; a DB-backed
ledger is the documented upgrade path for a multi-replica rollout. Only keyless builds pass through
here — a fully-keyed build is never reserved.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime


class DraftBuildRefusedError(Exception):
    """Base for a refused keyless build.

    Subclasses set two class attributes the router reads to map EVERY refusal the same way (one
    ``except`` clause, no per-reason branching): ``status_code`` (the HTTP status) and ``detail``
    (the learner-facing message). The base ``__init__`` seeds the exception message from ``detail``
    so logs/tracebacks carry the reason rather than a blank ``SomeError:``."""

    status_code: int = 403
    detail: str = "Draft builds are not available."

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.detail)


class DraftTierDisabledError(DraftBuildRefusedError):
    """The operator has switched the keyless Draft tier off; a keyless build is refused."""

    status_code = 403
    detail = "Draft (keyless) builds are disabled. Add a provider key in Settings to build."


class DraftDailyCapReachedError(DraftBuildRefusedError):
    """The tenant has used their per-day allowance of keyless builds."""

    status_code = 429

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.detail = (
            f"Daily Draft build limit reached ({cap}). Add a provider key to build without the "
            "cap, or try again tomorrow."
        )
        super().__init__(self.detail)


class DraftBuildBusyError(DraftBuildRefusedError):
    """A keyless build is already running; the shared runtime serves one at a time."""

    status_code = 429
    detail = (
        "A Draft build is already running. The local runtime serves one at a time — try again "
        "shortly."
    )


@dataclass(frozen=True)
class DraftReservation:
    """A held keyless-build slot — release it when the build's task ends (success or failure)."""

    owner_key: str
    day: str


class KeylessBuildThrottle:
    """In-process admission gate for keyless builds: operator switch + per-tenant per-day cap +
    concurrency limit. Reservations are synchronous (no awaiting), so check-and-reserve is atomic
    under the single-threaded event loop — no lock needed.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        daily_cap: int = 10,
        max_concurrent: int = 1,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._enabled = enabled
        self._daily_cap = daily_cap
        # At least one slot — a 0 here would refuse every keyless build without the honest
        # DraftTierDisabled signal; the operator disables the tier with the enabled flag, not a 0.
        self._max_concurrent = max(1, max_concurrent)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._active = 0
        # (owner_key, iso-day) -> builds started that day. Pruned to the current day on each reserve
        # so the map can't grow without bound across days.
        self._counts: dict[tuple[str, str], int] = {}

    def reserve(self, owner_key: str) -> DraftReservation:
        """Admit one keyless build for ``owner_key``, or refuse with the reason.

        Raises :class:`DraftTierDisabledError` when the operator disabled the tier,
        :class:`DraftBuildBusyError` when the concurrency limit is already in use, or
        :class:`DraftDailyCapReachedError` when the tenant has hit their per-day cap. On success the
        slot and the day's count are incremented; the caller MUST :meth:`release` when it ends.
        """
        if not self._enabled:
            raise DraftTierDisabledError
        if self._active >= self._max_concurrent:
            raise DraftBuildBusyError
        day = self._clock().date().isoformat()
        self._prune(day)
        used = self._counts.get((owner_key, day), 0)
        if used >= self._daily_cap:
            raise DraftDailyCapReachedError(self._daily_cap)
        self._counts[(owner_key, day)] = used + 1
        self._active += 1
        return DraftReservation(owner_key=owner_key, day=day)

    def release(self, reservation: DraftReservation) -> None:
        """Free the in-flight slot the build held. The day's count is intentionally NOT decremented
        — a completed build still counts against the daily cap. Idempotent-safe (floors at zero)."""
        self._active = max(0, self._active - 1)

    def _prune(self, today: str) -> None:
        """Drop count entries from earlier days so the cap resets and the map stays bounded."""
        stale = [key for key in self._counts if key[1] != today]
        for key in stale:
            del self._counts[key]
