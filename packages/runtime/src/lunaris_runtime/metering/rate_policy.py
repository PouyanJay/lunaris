from enum import StrEnum


class RatePolicy(StrEnum):
    PROVIDER_FALLBACK = "provider_fallback"
    EXACT_MODEL = "exact_model"
