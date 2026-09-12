from dataclasses import dataclass, field
from threading import RLock

from .claim import GraphClaim


@dataclass
class LocalTransactionState:
    claims: dict[tuple[str | None, str], GraphClaim] = field(default_factory=dict)
    receipts: set[tuple[str | None, str, str]] = field(default_factory=set)
    lock: RLock = field(default_factory=RLock)
