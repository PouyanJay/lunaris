from pydantic import Field

from .base import CourseModel
from .enums import Latency, Mode, QualityFloor, RiskCategory, RiskOverride, RiskTier


class Budget(CourseModel):
    max_usd: float = 5.0
    max_wall_clock_min: float = 30.0
    quality_floor: QualityFloor = QualityFloor.STANDARD


class CourseSettings(CourseModel):
    """Frozen at generation time so a course is reproducible from its settings."""

    latency: Latency = Latency.AWAIT_FULL
    mode: Mode = Mode.ARTIFACT
    budget: Budget = Field(default_factory=Budget)
    risk_override: RiskOverride = RiskOverride.AUTO
    load_budget_per_lesson: float = 5.0
    max_modules: int = 12


class RiskProfile(CourseModel):
    tier: RiskTier = RiskTier.LOW
    categories: list[RiskCategory] = Field(default_factory=list)
    rationale: str = ""


class BudgetLedger(CourseModel):
    spent_usd: float = 0.0
    projected_usd: float = 0.0
    rungs_applied: int = 0
