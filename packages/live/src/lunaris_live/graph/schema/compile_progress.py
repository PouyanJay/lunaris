from pydantic import Field

from .base import LiveModel
from .compile_phase import CompilePhase


class CompileProgress(LiveModel):
    """One beat of a compile in flight — what is happening, and how much of it is done.

    A cold compile runs for minutes, and this is what the learner watches for that whole time. It is
    deliberately a *measure* rather than a message: the copy for each phase belongs to the surface
    that renders it, so the wire carries counts the screen can format and never prose it has to
    display verbatim.
    """

    phase: CompilePhase
    #: Concepts finished. Meaningful only while authoring — 0 before the concepts are known.
    done: int = Field(default=0, ge=0)
    #: Concepts in total, or 0 while that is still unknown. A surface must handle the unknown
    #: total: a bar that divides by it would otherwise render the decomposition as NaN.
    total: int = Field(default=0, ge=0)
