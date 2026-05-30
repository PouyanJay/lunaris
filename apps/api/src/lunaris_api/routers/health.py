from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
