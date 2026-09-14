import math
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceLimits:
    concurrency: int = 2
    operations: int = 120
    reserve_usd: float = 3.0
    lease_seconds: int = 120
    session_seconds: int = 1800

    def __post_init__(self) -> None:
        if not (1 <= self.concurrency <= 2 and 1 <= self.operations <= 120):
            raise ValueError("Voice limits exceed supported bounds")
        if not math.isfinite(self.reserve_usd) or not 0 < self.reserve_usd <= 3:
            raise ValueError("Voice reservation limit must be in (0, 3]")
        if not 1 <= self.lease_seconds <= 120 or not 1 <= self.session_seconds <= 3600:
            raise ValueError("Voice deadlines exceed supported bounds")
