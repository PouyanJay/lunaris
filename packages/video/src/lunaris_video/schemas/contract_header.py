from pydantic import Field

from lunaris_video.schemas.base import ContractModel
from lunaris_video.schemas.global_style import GlobalStyle
from lunaris_video.schemas.voice_spec import VoiceSpec

_SPEC_VERIFIER_GATES: tuple[str, ...] = (
    "render_success_per_scene",
    "frame_visual_qa",
    "narration_claim_check_vs_sources",
)


def _default_verifier_gates() -> list[str]:
    return list(_SPEC_VERIFIER_GATES)


class ContractHeader(ContractModel):
    """The fields every contract shape shares — flat (lesson) and chaptered (overview) alike.

    ``verifier_gates`` defaults to the spec's three mandatory gates; a planner can only ADD
    gates by writing the field, never silently drop one by omitting it.
    """

    topic: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    visual_archetypes_used: list[str] = Field(min_length=1)
    asset_strategy: str = Field(min_length=1)
    global_style: GlobalStyle
    voice: VoiceSpec | None = None
    verifier_gates: list[str] = Field(default_factory=_default_verifier_gates, min_length=1)
