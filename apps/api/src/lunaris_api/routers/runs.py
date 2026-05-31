from fastapi import APIRouter, Query
from lunaris_runtime.schema import CourseRun

from ..dependencies import CourseServiceDep
from ..service import RUNS_LIMIT_DEFAULT, RUNS_LIMIT_MAX, RUNS_LIMIT_MIN

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[CourseRun])
async def list_runs(
    service: CourseServiceDep,
    limit: int = Query(default=RUNS_LIMIT_DEFAULT, ge=RUNS_LIMIT_MIN, le=RUNS_LIMIT_MAX),
) -> list[CourseRun]:
    """List recent course-build runs, newest first — the sidebar's history feed."""
    return await service.list_runs(limit=limit)
