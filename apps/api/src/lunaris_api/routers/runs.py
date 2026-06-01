from fastapi import APIRouter, HTTPException, Query, status
from lunaris_runtime.schema import CourseRun

from ..dependencies import CourseServiceDep
from ..service import (
    RUNS_LIMIT_DEFAULT,
    RUNS_LIMIT_MAX,
    RUNS_LIMIT_MIN,
    RunHistoryUnavailableError,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[CourseRun])
async def list_runs(
    service: CourseServiceDep,
    limit: int = Query(default=RUNS_LIMIT_DEFAULT, ge=RUNS_LIMIT_MIN, le=RUNS_LIMIT_MAX),
) -> list[CourseRun]:
    """List recent course-build runs, newest first — the sidebar's history feed.

    503 when the history backend is unreachable: an ``HTTPException`` is handled inside the CORS
    middleware, so the error response keeps its CORS headers and the sidebar shows its recoverable
    Retry state — unlike an unhandled 500, which escapes CORS and reads as a network failure.
    """
    try:
        return await service.list_runs(limit=limit)
    except RunHistoryUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Run history is temporarily unavailable",
        ) from exc
