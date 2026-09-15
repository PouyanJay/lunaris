from typing import Literal

from pydantic import Field

from .base import CorpusModel


class CorpusSection(CorpusModel):
    """Private compile-plane material; answer keys must never enter graph/API payloads."""

    locator: str = Field(min_length=1, max_length=300, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    text: str = Field(min_length=1, max_length=20000)
    kind: Literal["lesson", "assessment"]
    answer_key: str | None = Field(default=None, max_length=10000, repr=False)
