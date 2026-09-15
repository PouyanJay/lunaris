from typing import Literal

from pydantic import Field

from ...schemas.base import CorpusModel


class MappingDecision(CorpusModel):
    node_id: str = Field(min_length=1, max_length=100)
    locator: str = Field(min_length=1, max_length=300, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    status: Literal["approved", "rejected"]
    reason: Literal["verified", "verifier_rejected", "invalid_evidence", "missing_verdict"]
    evidence: tuple[str, ...] = Field(default=(), max_length=5)


class MappingGap(CorpusModel):
    node_id: str | None = None
    locator: str | None = None
    reason: Literal[
        "node_without_material",
        "unmapped_candidate",
        "candidate_limit",
        "context_limit",
        "video_unavailable",
        "invalid_proposal",
        "invalid_verdict",
        "untrusted_grounding",
        "mapping_failed",
        "source_text_truncated",
    ]


class MappingReport(CorpusModel):
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: str = Field(min_length=1, max_length=100)
    status: Literal["passed", "failed"]
    mapper_version: str = "mapping-v1"
    verifier_version: str = "mapping-verifier-v1"
    mappings: tuple[MappingDecision, ...] = Field(default=(), max_length=100)
    gaps: tuple[MappingGap, ...] = Field(default=(), max_length=2000)
    issues: tuple[str, ...] = Field(default=(), max_length=20)
