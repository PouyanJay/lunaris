from enum import StrEnum


class ModelTier(StrEnum):
    """Two tiers per D1: a strong planner/judge and a cheaper bulk worker."""

    STRONG = "strong"
    WORKER = "worker"
