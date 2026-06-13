from pydantic import Field

from lunaris_video.schemas.base import ContractModel

_HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"


class GlobalStyle(ContractModel):
    """The contract's design tokens — one ``global_style`` shared by every scene of a course.

    Populated from the enterprise-ui token map (plan principle 4: tokens flow one direction,
    product → video), never hand-picked per video. Field names follow the skill's contract spec.
    ``font`` must exist in the render environment (checked at render time, not here).
    """

    background: str = Field(pattern=_HEX_COLOR)
    primary_text: str = Field(pattern=_HEX_COLOR)
    muted: str = Field(pattern=_HEX_COLOR)
    accent: str = Field(pattern=_HEX_COLOR)
    danger: str = Field(pattern=_HEX_COLOR)
    success: str = Field(pattern=_HEX_COLOR)
    font: str = Field(min_length=1)
