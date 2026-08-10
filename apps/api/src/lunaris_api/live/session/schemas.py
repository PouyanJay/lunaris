from lunaris_live.session import MAX_ANSWER_CHARS
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


class AnswerRequest(BaseModel):
    """What the learner said in reply to the criterion the last turn staged.

    Bounded at both ends at the trust boundary. Empty is refused rather than graded as a miss: an
    empty POST is a client bug, and scoring it would lower a belief — and so change what the
    director teaches next — on the strength of a stray keystroke. The ceiling is generous enough for
    somebody explaining a concept properly and small enough that a pasted chapter never becomes a
    model prompt and a stored row.
    """

    # Stripped BEFORE the length check, or " " passes it and reaches the grader as "" — which the
    # stub scores NOT_MET, lowering a belief and changing what the director teaches next on the
    # strength of one stray keystroke. The bound is the domain's, imported rather than restated.
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, str_strip_whitespace=True
    )

    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    #: The turn the learner was looking at. Required, not inferred: a double-submit would otherwise
    #: be graded against the question that replaced it, and the words would go into the record under
    #: a criterion they were never written for.
    answering_seq: int = Field(ge=1)
