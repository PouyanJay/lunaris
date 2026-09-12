from typing import Annotated, Literal

from pydantic import Field

from ...graph.schema.base import LiveModel


class VerificationReport(LiveModel):
    version: Literal[1] = 1
    verifier_version: str = "chromium-contract-v2"
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    spec_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved: bool
    checks_passed: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list, max_length=20)
    elapsed_ms: int = Field(ge=0)
    screenshots: list[Annotated[str, Field(min_length=1, max_length=5_000_000)]] = Field(
        default_factory=list, max_length=2
    )
