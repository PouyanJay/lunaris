from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from lunaris_runtime.logging import bind_request_id
from lunaris_runtime.schema import CourseRun

from ..dependencies import CourseServiceDep
from ..service import (
    RUNS_LIMIT_DEFAULT,
    RUNS_LIMIT_MAX,
    RUNS_LIMIT_MIN,
    RunHistoryUnavailableError,
    RunNotCancellableError,
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


@router.post("/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(run_id: str, service: CourseServiceDep) -> Response:
    """Request cancellation of an in-flight build. 202 Accepted once signalled (the run flips to
    CANCELLED as its task unwinds); 404 when the run isn't in-flight (unknown or already terminal).
    A request_id is bound + returned in X-Request-Id for cross-layer log correlation.
    """
    request_id = uuid4().hex
    bind_request_id(request_id)
    headers = {"X-Request-Id": request_id}
    try:
        await service.cancel_run(run_id)
    except RunNotCancellableError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No in-flight run to cancel",
            headers=headers,
        ) from exc
    return Response(status_code=status.HTTP_202_ACCEPTED, headers=headers)
