from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .candidate import SimCandidate
from .teaching_spec import TeachingSpec
from .verification_report import VerificationReport
from .verified_bundle import VerifiedBundle
from .visual_verdict import SimVisualVerdict


class SimBuildCall(LiveModel):
    stage: Literal["plan", "generate", "review"]
    model: str
    prompt_version: str = "sim-factory-v3"
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reserved_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    outcome: Literal["started", "succeeded", "failed", "indeterminate"] = "succeeded"


class SimBuildResult(LiveModel):
    status: Literal["approved", "rejected", "unsuitable"]
    bundle: VerifiedBundle | None = None
    spec: TeachingSpec | None = None
    calls: list[SimBuildCall] = Field(default_factory=list)
    candidates: list[SimCandidate] = Field(default_factory=list, max_length=3)
    reports: list[VerificationReport] = Field(default_factory=list)
    visual_reviews: list[SimVisualVerdict] = Field(default_factory=list)
    reason: str | None = None
    elapsed_ms: int = Field(ge=0)
