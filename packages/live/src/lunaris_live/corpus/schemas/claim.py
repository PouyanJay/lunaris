from typing import Literal

from pydantic import Field

from .base import CorpusModel


class CorpusClaim(CorpusModel):
    text: str = Field(min_length=1, max_length=20000)
    citation_id: str | None = Field(default=None, max_length=300)
    status: Literal["unverified", "supported", "revise", "cut"] = "unverified"
