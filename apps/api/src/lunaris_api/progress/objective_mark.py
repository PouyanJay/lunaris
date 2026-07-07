from dataclasses import dataclass
from datetime import datetime

# Objectives carry no id in the course schema, so a mark is keyed by the objective's position in
# its module's objectives array — stable across reads of the same course payload (a rebuild that
# reorders objectives orphans the mark, which is acceptable: progress is per built course).


@dataclass(frozen=True)
class ObjectiveMark:
    """One understood objective: the learner marked module ``module_id``'s ``objective_index``."""

    course_id: str
    module_id: str
    objective_index: int
    understood_at: datetime
