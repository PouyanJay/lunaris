from fastapi import APIRouter

from ..dependencies import CurrentUserIdDep
from ..schemas.me import MeResponse

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def get_me(user_id: CurrentUserIdDep) -> MeResponse:
    return MeResponse(user_id=user_id)
