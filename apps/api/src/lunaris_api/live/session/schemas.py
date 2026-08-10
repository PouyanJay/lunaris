from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class SessionStartRequest(BaseModel):
    """Open a session on a map the learner already has.

    The graph id and nothing else: everything the session needs to teach is already on the map, and
    a request carrying teaching preferences would be configuring the tutor at the door rather than
    letting the director learn them from what the learner does (P2c's placement interview is where
    priors come from).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    graph_id: str = Field(min_length=1, max_length=100)
