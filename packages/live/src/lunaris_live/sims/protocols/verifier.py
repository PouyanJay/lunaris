from typing import Protocol

from ..schema.candidate import SimCandidate
from ..schema.teaching_spec import TeachingSpec
from ..schema.verification_report import VerificationReport


class ISimVerifier(Protocol):
    async def verify(self, candidate: SimCandidate, spec: TeachingSpec) -> VerificationReport: ...
