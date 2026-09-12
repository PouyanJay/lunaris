from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel


class VerificationReport(LiveModel):
    version: Literal[1] = 1
    verifier_version: str = "chromium-contract-v1"
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    spec_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved: bool
    checks_passed: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list, max_length=20)
    elapsed_ms: int = Field(ge=0)
