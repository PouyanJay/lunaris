from typing import Annotated

from fastapi import Depends
from lunaris_live.sims.registry.protocols.asset_store import ISimAssetStore
from lunaris_live.sims.registry.supabase_asset_store import SupabaseSimAssetStore

from ...config import Settings, get_settings

_store = SupabaseSimAssetStore()


def get_sim_asset_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ISimAssetStore | None:
    return _store if settings.has_supabase else None
