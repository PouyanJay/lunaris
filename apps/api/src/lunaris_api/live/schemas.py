from pydantic import BaseModel, Field, field_validator


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
