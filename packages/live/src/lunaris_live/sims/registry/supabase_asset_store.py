from uuid import UUID, uuid4

from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard

from ..schema.build_result import SimBuildResult
from .models.build_claim import SimBuildClaim
from .schema.asset import SimAsset


class SupabaseSimAssetStore:
    """Immutable approved code and atomic build claims; every service-role read is scoped."""

    def __init__(self, *, client: object | None = None) -> None:
        self._client = client

    def _db(self) -> object:
        if self._client is None:
            self._client = supabase_client(
                url_env="SUPABASE_URL",
                service_key_env="SUPABASE_SERVICE_ROLE_KEY",
                purpose="persist simulator assets",
            )
        return self._client

    def _visible(self, query: object, owner_id: str | None) -> object:
        owner = str(UUID(owner_id)) if owner_id else None
        rule = f"owner_id.eq.{owner},public_source.not.is.null" if owner else "owner_id.is.null"
        return query.eq("revoked", False).or_(rule)  # type: ignore[attr-defined]

    @guard("live_sim_assets find")
    def find(self, keys: list[str], *, owner_id: str | None) -> list[SimAsset]:
        if not keys:
            return []
        if len(keys) > 100:
            raise ValueError("Preload at most 100 teaching identities per request.")
        query = self._db().table("live_sim_assets").select("payload").in_("cache_key", keys)  # type: ignore[attr-defined]
        rows = self._visible(query, owner_id).execute().data or []  # type: ignore[attr-defined]
        assets = [SimAsset.model_validate(row["payload"]) for row in rows]
        # An owner's compatible artifact takes precedence over the public catalog.
        return sorted(assets, key=lambda asset: asset.public_source is None)

    @guard("live_sim_assets load")
    def load(self, asset_id: str, *, owner_id: str | None) -> SimAsset:
        query = self._db().table("live_sim_assets").select("payload").eq("id", str(UUID(asset_id)))  # type: ignore[attr-defined]
        rows = self._visible(query, owner_id).execute().data or []  # type: ignore[attr-defined]
        if not rows:
            raise FileNotFoundError("No such approved simulator")
        return SimAsset.model_validate(rows[0]["payload"])

    @guard("live_sim_builds claim")
    def claim(
        self, cache_key: str, *, owner_id: str | None, public_source: str | None = None
    ) -> SimBuildClaim | None:
        owner = UUID(owner_id) if owner_id else None
        if owner and public_source is not None:
            raise ValueError("Private source cannot become public.")
        result = (
            self._db()
            .rpc(  # type: ignore[attr-defined]
                "claim_live_sim",
                {
                    "p_owner": str(owner) if owner else None,
                    "p_public_source": public_source,
                    "p_cache_key": cache_key,
                },
            )
            .execute()
            .data
        )
        if "token" not in result:
            return None
        return SimBuildClaim(UUID(result["token"]), cache_key, owner, public_source)

    def _asset(self, claim: SimBuildClaim, result: SimBuildResult) -> SimAsset | None:
        if result.status != "approved":
            return None
        if result.bundle is None:
            raise ValueError("Approved result requires evidence.")
        asset = SimAsset(
            id=uuid4(),
            owner_id=claim.owner_id,
            public_source=claim.public_source,
            cache_key=claim.cache_key,
            bundle=result.bundle,
            calls=result.calls,
        )
        # Revalidate even when a caller used model_copy or mutated nested data.
        return SimAsset.model_validate_json(asset.model_dump_json())

    def _outcome(self, result: SimBuildResult, asset: SimAsset | None) -> str:
        if any(call.outcome == "indeterminate" for call in result.calls):
            if asset:
                raise ValueError("Indeterminate paid work cannot be published.")
            return "indeterminate"
        return "approved" if asset else "rejected"

    @guard("live_sim_builds finish")
    def finish(self, claim: SimBuildClaim, result: SimBuildResult) -> SimAsset | None:
        asset = self._asset(claim, result)
        outcome = self._outcome(result, asset)
        payload = (asset or result).model_dump(mode="json", by_alias=True)
        self._db().rpc(  # type: ignore[attr-defined]
            "finish_live_sim",
            {
                "p_owner": str(claim.owner_id) if claim.owner_id else None,
                "p_public_source": claim.public_source,
                "p_cache_key": claim.cache_key,
                "p_token": str(claim.token),
                "p_status": outcome,
                "p_asset": payload,
            },
        ).execute()
        return asset

    @guard("live_sim_assets revoke")
    def revoke(
        self, asset_id: str, *, owner_id: str | None, public_source: str | None = None
    ) -> None:
        query = (
            self._db()
            .table("live_sim_assets")
            .update({"revoked": True})
            .eq("id", str(UUID(asset_id)))
        )  # type: ignore[attr-defined]
        query = (
            query.eq("owner_id", str(UUID(owner_id))) if owner_id else query.is_("owner_id", None)
        )
        query = (
            query.eq("public_source", public_source)
            if public_source
            else query.is_("public_source", None)
        )
        if not query.execute().data:
            raise FileNotFoundError("No such simulator to revoke")
