from dataclasses import dataclass

from ..schemas.proposal import MappingProposal
from ..schemas.verdict import MappingVerdicts


@dataclass(frozen=True)
class MappingJudgment:
    proposal: MappingProposal
    verdicts: MappingVerdicts
