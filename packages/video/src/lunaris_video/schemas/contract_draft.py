from pydantic import Field

from lunaris_video.schemas.base import ContractModel
from lunaris_video.schemas.scene_contract import SceneContract


class ContractDraft(ContractModel):
    """What the PLANNING MODEL is allowed to emit — the contract minus the injected fields.

    ``global_style`` (token map), ``voice`` (config, V3) and ``verifier_gates`` (spec
    constants) are system-owned: they are absent here so a completion that tries to set them
    fails validation (``extra="forbid"``) and gets a repair turn, instead of silently
    overriding product decisions. The PLAN node composes the full ``SceneContracts`` from this
    draft plus the injected values.
    """

    topic: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    visual_archetypes_used: list[str] = Field(min_length=1)
    asset_strategy: str = Field(min_length=1)
    scenes: list[SceneContract] = Field(min_length=1)
