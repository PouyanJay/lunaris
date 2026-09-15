from dataclasses import dataclass

from ..schemas.report import MappingDecision


@dataclass(frozen=True)
class MappingReview:
    decisions: tuple[MappingDecision, ...]
    issues: tuple[str, ...]
