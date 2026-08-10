from pydantic import Field

from ...graph.schema.base import LiveModel
from .evidence_kind import EvidenceKind


class TurnGrade(LiveModel):
    """What one answer was judged to show, and why.

    The reason is not decoration and not for the model: a learner being told they have not met a
    bar needs to know what was missing, and a human auditing a session needs to be able to tell a
    grader that is quietly wrong from a learner who is quietly lost. It is the grader's counterpart
    to ``DirectorMove.reason``.
    """

    kind: EvidenceKind
    reason: str = Field(min_length=1, max_length=500)
