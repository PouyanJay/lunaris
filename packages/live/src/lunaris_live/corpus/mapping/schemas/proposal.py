from pydantic import Field

from ...schemas.base import CorpusModel


class ProposedMapping(CorpusModel):
    node_id: str = Field(min_length=1, max_length=100)
    locator: str = Field(min_length=1, max_length=300)


class MappingProposal(CorpusModel):
    mappings: tuple[ProposedMapping, ...] = Field(max_length=100)
