from dataclasses import dataclass


@dataclass(frozen=True)
class GraphClaim:
    graph_id: str
    owner_id: str | None
    token: str
