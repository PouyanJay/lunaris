from dataclasses import dataclass


@dataclass(frozen=True)
class RecordedAudio:
    data: bytes
    duration_s: float
