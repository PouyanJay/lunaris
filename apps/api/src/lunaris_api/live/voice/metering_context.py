from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceMeteringContext:
    session_id: str
    owner_id: str | None
    session_cost_ceiling_usd: float = 0
