import math
from dataclasses import dataclass


@dataclass(frozen=True)
class VoicePolicy:
    """Conservative admission estimates, explicitly separate from measured provider pricing."""

    speech_provider: str = "elevenlabs"
    speech_model: str = "eleven_flash_v2_5"
    voice_version: str = "george-flash-v1"
    stt_reserve_per_second: float = 0.001
    tts_reserve_per_char: float = 0.0003
    operation_timeout_s: float = 90.0
    cleanup_timeout_s: float = 5.0
    max_audio_bytes: int = 5_760_000

    def __post_init__(self) -> None:
        rates = (self.stt_reserve_per_second, self.tts_reserve_per_char)
        if any(not math.isfinite(rate) or rate <= 0 for rate in rates):
            raise ValueError("Voice reservation estimates must be positive and finite")
        if not 1 <= self.operation_timeout_s <= 90 or not 0 < self.cleanup_timeout_s <= 5:
            raise ValueError("Voice timeouts exceed supported bounds")
        if not 2 <= self.max_audio_bytes <= 5_760_000 or self.max_audio_bytes % 2:
            raise ValueError("Voice audio limit must contain bounded complete PCM samples")
        if not all(
            0 < len(value) <= 100
            for value in (self.speech_provider, self.speech_model, self.voice_version)
        ):
            raise ValueError("Voice provenance and version are required")
