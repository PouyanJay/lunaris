from dataclasses import dataclass

from ....graph import ConceptGraph


@dataclass(frozen=True)
class SimPreparation:
    graph: ConceptGraph
    node_id: str
    session_id: str
    owner_id: str | None
