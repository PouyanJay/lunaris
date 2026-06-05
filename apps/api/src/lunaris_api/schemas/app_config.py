from typing import Literal

from pydantic import Field

from .base import CamelModel


class ConfigSettingView(CamelModel):
    """One non-secret config setting on the wire: its value is SHOWN (unlike a secret), with its
    default, how to render it (toggle / text / model), and whether a change needs a restart."""

    name: str
    value: str
    default: str
    kind: Literal["toggle", "text", "model"]
    restart_required: bool


class ConfigView(CamelModel):
    """The non-secret configuration surface: every editable setting with its current value."""

    settings: list[ConfigSettingView]


class ConfigValue(CamelModel):
    """Request body for updating one config setting. Length-capped at the trust boundary; the store
    applies the per-kind rules (toggle ∈ {true,false}; text/model non-empty)."""

    value: str = Field(max_length=200)
