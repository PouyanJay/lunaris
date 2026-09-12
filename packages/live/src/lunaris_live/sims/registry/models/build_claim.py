from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SimBuildClaim:
    token: UUID
    cache_key: str
    owner_id: UUID | None
    public_source: str | None
