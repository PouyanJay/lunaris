from pydantic import Field

from ....graph.schema import ConceptNode, MasteryCriterion
from ....graph.schema.base import LiveModel


class SimRequest(LiveModel):
    node: ConceptNode
    criterion: MasteryCriterion
    run_id: str = Field(min_length=1, max_length=100)
