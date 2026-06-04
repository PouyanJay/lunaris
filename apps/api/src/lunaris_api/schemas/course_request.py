from lunaris_runtime.schema import Clarification, DiscoveryDepth
from pydantic import BaseModel, Field, field_validator


class CourseRequest(BaseModel):
    """Request body for generating a course: the raw topic + the learner's opt-in confirm answers.

    ``clarification`` (P7.5) is the optional calibrated answers from the interpret clarifier; absent
    (the default one-click build) the pipeline uses the interpreter's inference verbatim.
    ``discovery_depth`` (P6.3) pre-authorizes how hard auto-discovery searches; STANDARD is the
    moderate one-click default, THOROUGH widens the grounding budget.
    """

    topic: str = Field(min_length=1, max_length=200)
    clarification: Clarification | None = None
    discovery_depth: DiscoveryDepth = DiscoveryDepth.STANDARD

    @field_validator("topic")
    @classmethod
    def _topic_not_blank(cls, value: str) -> str:
        """Reject an all-whitespace topic at the boundary (``min_length`` alone admits ``"   "``),
        so the brief endpoint never derives a blank subject/goal from it."""
        if not value.strip():
            raise ValueError("topic must not be blank")
        return value
