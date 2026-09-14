from pydantic import BaseModel, ConfigDict, Field, model_validator


class VoiceResult(BaseModel):
    """Only derived text or generated PCM references cross the persistence boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    text: str | None = Field(default=None, min_length=1, max_length=4000)
    audio_key: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}\.pcm$")
    audio_bytes: int | None = Field(default=None, ge=2, le=11_520_000)
    sample_rate: int | None = Field(default=None, ge=24000, le=24000)

    @model_validator(mode="after")
    def valid_variant(self) -> "VoiceResult":
        if self.audio_key is None:
            if self.text is None or self.audio_bytes is not None or self.sample_rate is not None:
                raise ValueError("A transcript result requires text only")
        elif self.text is not None or self.audio_bytes is None or self.sample_rate is None:
            raise ValueError("An audio result requires PCM metadata only")
        elif self.audio_bytes % 2:
            raise ValueError("PCM requires complete samples")
        return self
