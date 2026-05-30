from pydantic import Field

from .base import CourseModel
from .enums import Pace


class Probe(CourseModel):
    kc: str
    result: bool
    confidence: float = Field(ge=0, le=1)


class Prefs(CourseModel):
    pace: Pace = Pace.NORMAL
    tone: str = ""


class LearnerModel(CourseModel):
    """Diagnostic output. MVP uses a fixed/empty frontier (assume novice)."""

    goal: str = ""
    time_budget_min: int = 0
    frontier: list[str] = Field(default_factory=list)  # recursively discovered boundary
    probes: list[Probe] = Field(default_factory=list)
    prefs: Prefs = Field(default_factory=Prefs)


class MasteryHistoryEntry(CourseModel):
    item: str
    correct: bool
    at: str  # ISO timestamp


class MasteryState(CourseModel):
    """Runtime only (V2)."""

    per_kc: dict[str, float] = Field(default_factory=dict)
    history: list[MasteryHistoryEntry] = Field(default_factory=list)
