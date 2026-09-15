from dataclasses import dataclass

from ..schemas.report import MappingGap
from .candidate import MappingCandidate


@dataclass(frozen=True)
class MappingContext:
    candidates: tuple[MappingCandidate, ...]
    prompt_data: str
    source_nodes: frozenset[str]
    gaps: tuple[MappingGap, ...]
