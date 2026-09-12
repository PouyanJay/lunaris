from pydantic import model_validator

from ...graph.schema.base import LiveModel
from ..content_hash import content_hash
from .candidate import SimCandidate
from .teaching_spec import TeachingSpec
from .verification_report import VerificationReport
from .visual_verdict import SimVisualVerdict


class VerifiedBundle(LiveModel):
    """The publication boundary rejects mismatched or failed verification evidence."""

    candidate: SimCandidate
    spec: TeachingSpec
    report: VerificationReport
    visual_verdict: SimVisualVerdict

    @model_validator(mode="after")
    def verified_content(self) -> "VerifiedBundle":
        if not self.visual_verdict.passed or self.visual_verdict.content_hash != content_hash(
            self.candidate.html
        ):
            raise ValueError("Visual approval must match the candidate.")
        minimum_checks = 1 + sum(len(case.outputs) for case in self.spec.cases)
        if (
            not self.report.approved
            or self.report.reasons
            or self.report.verifier_version not in {"chromium-contract-v1", "chromium-contract-v2"}
            or self.report.checks_passed < minimum_checks
            or self.report.content_hash != content_hash(self.candidate.html)
            or self.report.spec_hash != content_hash(self.spec.model_dump_json(by_alias=True))
        ):
            raise ValueError("Only the exact independently verified bundle may be published.")
        return self
