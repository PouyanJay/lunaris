from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class CompileFailure(BaseModel):
    """Why a streamed compile stopped — the terminal frame of a stream that failed.

    A stream sends its status code before the work starts, so a failure can only ever be said in the
    body. This carries the run id with it because a failed compile is precisely when someone needs
    to go and read the logs for it, and the header is long gone by the time the web shows the error.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    message: str
    run_id: str


class LiveGraphRequest(BaseModel):
    """Request body for compiling a Lunaris Live concept graph: just the topic.

    Live's promise is that a topic is the only required input (plan §5) — a corpus is optional and
    arrives in Phase 5, and session config arrives with the session in Phase 2.
    """

    topic: str = Field(min_length=1, max_length=200)

    @field_validator("topic")
    @classmethod
    def _topic_not_blank(cls, value: str) -> str:
        """Reject an all-whitespace topic at the boundary — ``min_length`` alone admits ``"   "``,
        which would compile a graph about nothing and bill for it."""
        if not value.strip():
            raise ValueError("topic must not be blank")
        return value


class LiveGraphExtendRequest(BaseModel):
    """What a session sends when the learner asks for something the map does not cover (C1).

    ``anchors`` is where the tutor believes the request attaches — the concepts the learner already
    has. It is a hint recorded in the edit log, not a constraint: unknown ids are ignored rather
    than refused, because a tutor guessing wrongly about attachment should cost accuracy in the
    history, never the answer itself.
    """

    request: str = Field(min_length=1, max_length=500)
    anchors: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("request")
    @classmethod
    def _request_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("request must not be blank")
        return value
