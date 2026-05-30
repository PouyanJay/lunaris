from pydantic import BaseModel, Field


class CourseRequest(BaseModel):
    """Request body for generating a course: the raw topic the learner wants taught."""

    topic: str = Field(min_length=1, max_length=200)
