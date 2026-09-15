from typing import Annotated

from pydantic import Field, StrictBool

from ...schemas.base import CorpusModel


class MappingVerdict(CorpusModel):
    node_id: str = Field(min_length=1, max_length=100)
    locator: str = Field(min_length=1, max_length=300)
    approved: StrictBool
    evidence: tuple[Annotated[str, Field(min_length=1, max_length=2000)], ...] = Field(
        default=(), max_length=5
    )


class MappingVerdicts(CorpusModel):
    mappings: tuple[MappingVerdict, ...] = Field(max_length=100)
