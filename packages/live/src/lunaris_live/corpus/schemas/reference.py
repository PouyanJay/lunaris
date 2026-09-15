from pydantic import Field

from .base import CorpusModel


class CorpusReference(CorpusModel):
    course_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
