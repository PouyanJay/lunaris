from typing import Protocol

from ...schema.build_result import SimBuildResult
from ..models.build_claim import SimBuildClaim
from ..schema.asset import SimAsset


class ISimAssetStore(Protocol):
    def find(self, keys: list[str], *, owner_id: str | None) -> list[SimAsset]: ...
    def load(self, asset_id: str, *, owner_id: str | None) -> SimAsset: ...
    def claim(
        self, cache_key: str, *, owner_id: str | None, public_source: str | None = None
    ) -> SimBuildClaim | None: ...
    def finish(self, claim: SimBuildClaim, result: SimBuildResult) -> SimAsset | None: ...
    def revoke(
        self, asset_id: str, *, owner_id: str | None, public_source: str | None = None
    ) -> None: ...
