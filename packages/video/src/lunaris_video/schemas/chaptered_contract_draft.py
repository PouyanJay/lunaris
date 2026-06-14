from pydantic import Field

from lunaris_video.schemas.base import ContractModel
from lunaris_video.schemas.chapter import Chapter


class ChapteredContractDraft(ContractModel):
    """What the PLANNING MODEL is allowed to emit for the chaptered (OVERVIEW) kind.

    The chaptered analogue of ``ContractDraft``: the model writes everything creative (topic,
    audience, archetypes, and the chapters of scenes), while ``global_style`` (token map) and
    ``verifier_gates`` (spec constants) are system-owned — absent here so a completion that tries to
    set them fails validation (``extra="forbid"``) and earns a repair turn. The PLAN node composes
    the full ``ChapteredSceneContracts`` from this draft plus the injected values.
    """

    topic: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    visual_archetypes_used: list[str] = Field(min_length=1)
    asset_strategy: str = Field(min_length=1)
    chapters: list[Chapter] = Field(min_length=1)
