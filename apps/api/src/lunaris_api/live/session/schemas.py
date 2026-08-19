from lunaris_live.session import MAX_ANSWER_CHARS
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class SessionStartRequest(BaseModel):
    """Open a session: on a map the learner already has, or on a topic whose map does not exist yet.

    Exactly one of the two (U1). ``graph_id`` is P2a's opening — everything the session needs to
    teach is already on the map, and it starts teaching from turn 1. ``topic`` is P2c's: the compile
    is launched *and* the learner is interviewed while it runs, so nobody watches a progress bar,
    and the interview is what seeds the learner model with priors (T3). Neither request carries
    teaching preferences: the director learns those from what the learner does and says, not from
    a form at the door.

    Both named would have to pick one; neither has nothing to open. Both are refused here rather
    than resolved by a default, because a default here would be a policy nobody chose.
    """

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, str_strip_whitespace=True
    )

    graph_id: str | None = Field(default=None, min_length=1, max_length=100)
    topic: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _exactly_one_opening(self) -> "SessionStartRequest":
        if (self.graph_id is None) == (self.topic is None):
            raise ValueError("name exactly one of graphId or topic")
        return self


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
