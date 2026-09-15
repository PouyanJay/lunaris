from dataclasses import dataclass


@dataclass(frozen=True)
class MeasuredMedia:
    duration_s: float
    digest: str
    byte_count: int
