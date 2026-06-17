from typing import Annotated

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..dependencies import CurrentUserClaimsDep
from ..schemas.me import MeResponse

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def get_me(
    claims: CurrentUserClaimsDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeResponse:
    return MeResponse(user_id=claims.user_id, is_admin=settings.is_admin(claims.email))
