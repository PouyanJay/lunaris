from typing import Literal

from pydantic import Field

from .base import CorpusModel


class NodeGrounding(CorpusModel):
    node_id: str = Field(min_length=1, max_length=100)
    classification: Literal["source", "prerequisite", "unsupported"]
    locators: tuple[str, ...] = Field(default=(), max_length=1000)
    rationale: str = Field(default="", max_length=2000)


class GroundingReport(CorpusModel):
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: str = Field(min_length=1, max_length=100)
    status: Literal["passed", "failed"]
    nodes: tuple[NodeGrounding, ...] = Field(default=(), max_length=1000)
    uncovered_locators: tuple[str, ...] = Field(default=(), max_length=1000)
    omitted_locators: tuple[str, ...] = Field(default=(), max_length=1000)
    issues: tuple[str, ...] = Field(default=(), max_length=100)
