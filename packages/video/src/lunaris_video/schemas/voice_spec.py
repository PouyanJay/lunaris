from pydantic import Field

from lunaris_video.schemas.base import ContractModel


class VoiceSpec(ContractModel):
    """Optional narration voice for a contract — present only when voiced output is wanted.

    V1 renders silent (voice lands in V3), but the field is part of the pinned contract spec,
    so the schema carries it from day one: a contract written today stays valid when narration
    is added later. One voice per course for consistency (spec rule).
    """

    provider: str = Field(min_length=1)
    voice_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
