from uuid import UUID

from pydantic import Field, model_validator

from ....graph.schema.base import LiveModel
from ...schema.build_result import SimBuildCall
from ...schema.verified_bundle import VerifiedBundle


class SimAsset(LiveModel):
    id: UUID
    owner_id: UUID | None = None
    public_source: str | None = Field(default=None, min_length=1, max_length=1000)
    cache_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    bundle: VerifiedBundle
    calls: list[SimBuildCall] = Field(min_length=1, max_length=10)
    revoked: bool = False

    @model_validator(mode="after")
    def private_source_stays_private(self) -> "SimAsset":
        if self.owner_id is not None and self.public_source is not None:
            raise ValueError("An owner-scoped private artifact cannot be published as public.")
        return self
