import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from lunaris_live.sims.registry.protocols.asset_store import ISimAssetStore
from lunaris_live.sims.sandbox_policy import SIM_CSP
from lunaris_runtime.persistence import PersistenceError

from ...dependencies import OptionalUserIdDep
from .sim_asset_dependencies import get_sim_asset_store

router = APIRouter(prefix="/api/live/sims/assets", tags=["live"])


@router.get("/{asset_id}", response_class=Response)
async def approved_simulator(
    asset_id: UUID,
    owner_id: OptionalUserIdDep,
    store: Annotated[ISimAssetStore | None, Depends(get_sim_asset_store)],
) -> Response:
    """Fetch approved HTML with bearer authentication and a fresh revocation check."""
    if store is None:
        raise HTTPException(404, "No such approved simulator")
    try:
        asset = await asyncio.to_thread(store.load, str(asset_id), owner_id=owner_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "No such approved simulator") from exc
    except PersistenceError as exc:
        raise HTTPException(503, "Simulator storage temporarily unavailable") from exc
    return Response(
        asset.bundle.candidate.html,
        media_type="text/html",
        headers={
            "Content-Security-Policy": SIM_CSP,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
        },
    )
