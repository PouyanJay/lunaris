from typing import Literal

from pydantic import Field

from .base import CorpusModel


class SourceQuote(CorpusModel):
    locator: str = Field(min_length=1, max_length=300)
    quote: str = Field(min_length=1, max_length=2000)


class NodeVerdict(CorpusModel):
    node_id: str = Field(min_length=1, max_length=100)
    classification: Literal["source", "prerequisite", "unsupported"]
    supported: bool
    evidence: tuple[SourceQuote, ...] = Field(default=(), max_length=100)
    rationale: str = Field(min_length=1, max_length=2000)


class VerificationVerdict(CorpusModel):
    nodes: tuple[NodeVerdict, ...] = Field(max_length=20)
